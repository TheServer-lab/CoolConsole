from __future__ import annotations

import locale
import os
import shlex
import threading
from pathlib import Path

from PyQt6.QtCore import QObject, QProcess, pyqtSignal

try:
    from winpty import PtyProcess
except ImportError:
    PtyProcess = None


class CommandRunner(QObject):
    output_received = pyqtSignal(str, str)
    command_started = pyqtSignal(str)
    command_finished = pyqtSignal(int)
    cwd_changed = pyqtSignal(str)
    clear_requested = pyqtSignal()
    shell_changed = pyqtSignal(str)
    session_changed = pyqtSignal(bool)
    backend_changed = pyqtSignal(str)

    def __init__(self, start_dir: Path | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.cwd = Path(start_dir or Path.cwd())
        self.encoding = locale.getpreferredencoding(False) or "utf-8"
        self.shell_mode = "cmd" if os.name == "nt" else "sh"
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read_output)
        self.process.finished.connect(self._on_finished)
        self.process.errorOccurred.connect(self._on_error)
        self._stdout_buffer = b""
        self.session_active = False
        self.backend_mode = "conpty" if os.name == "nt" and PtyProcess is not None else "process"
        self._pty_process = None
        self._pty_reader: threading.Thread | None = None
        self._pty_buffer = ""

    def is_running(self) -> bool:
        if self._pty_process is not None:
            try:
                return self._pty_process.isalive()
            except Exception:
                return False
        return self.process.state() != QProcess.ProcessState.NotRunning

    def run_command(self, command: str) -> bool:
        command = command.strip()
        if not command:
            return False

        if self._handle_builtin(command):
            return True

        if self.session_active:
            if not self.is_running():
                self.start_session()
            if not self.is_running():
                return False
            self.command_started.emit(command)
            self._write_session(command + "\n")
            self.command_finished.emit(0)
            return True

        if self.is_running():
            return False

        self._stdout_buffer = b""
        self.process.setWorkingDirectory(str(self.cwd))
        self.command_started.emit(command)

        if os.name == "nt":
            if self.shell_mode == "powershell":
                self.process.start(
                    "powershell.exe",
                    ["-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                )
            else:
                self.process.start("cmd.exe", ["/Q", "/C", command])
        else:
            self.process.start("/bin/sh", ["-lc", command])
        return True

    def start_session(self) -> bool:
        if self.session_active and self.is_running():
            return True
        if self.is_running():
            return False

        self._stdout_buffer = b""
        if self.backend_mode == "conpty" and os.name == "nt" and PtyProcess is not None:
            argv = self._session_argv()
            cols = 120
            rows = 32
            self._pty_process = PtyProcess.spawn(argv, cwd=str(self.cwd), dimensions=(rows, cols), backend="conpty")
            self._pty_buffer = ""
            self._pty_reader = threading.Thread(target=self._read_pty_loop, daemon=True)
            self._pty_reader.start()
        else:
            self.process.setWorkingDirectory(str(self.cwd))
            if os.name == "nt":
                if self.shell_mode == "powershell":
                    self.process.start(
                        "powershell.exe",
                        [
                            "-NoLogo",
                            "-NoProfile",
                            "-NoExit",
                            "-ExecutionPolicy",
                            "Bypass",
                            "-Command",
                            "function prompt { \"$pwd> \" }",
                        ],
                    )
                else:
                    self.process.start("cmd.exe", ["/Q", "/K", "prompt", "$P$G"])
            else:
                self.process.start("/bin/sh", ["-i"])
        self.session_active = True
        self.session_changed.emit(True)
        return True

    def stop_session(self) -> None:
        if self._pty_process is not None:
            try:
                self._pty_process.write("exit\r\n")
            except Exception:
                pass
            try:
                self._pty_process.terminate()
            except Exception:
                pass
            self._pty_process = None
            self._pty_reader = None
        elif self.is_running():
            try:
                self.process.write(b"exit\n")
                self.process.waitForFinished(600)
            except Exception:
                pass
            if self.is_running():
                self.process.kill()
                self.process.waitForFinished(1000)
        if self.session_active:
            self.session_active = False
            self.session_changed.emit(False)

    def stop(self) -> None:
        if self._pty_process is not None:
            try:
                self._pty_process.sendintr()
            except Exception:
                try:
                    self._pty_process.terminate()
                except Exception:
                    pass
            return
        if not self.is_running():
            return
        self.process.kill()
        self.process.waitForFinished(1000)
        if self.session_active:
            self.session_active = False
            self.session_changed.emit(False)

    def set_backend_mode(self, backend: str) -> None:
        if backend not in {"process", "conpty"}:
            return
        if backend == "conpty" and (os.name != "nt" or PtyProcess is None):
            self.output_received.emit("ConPTY backend is not available.", "error")
            return
        if self.session_active:
            self.stop_session()
        self.backend_mode = backend
        self.backend_changed.emit(self.backend_mode)

    def supports_backend(self, backend: str) -> bool:
        if backend == "conpty":
            return os.name == "nt" and PtyProcess is not None
        return backend == "process"

    def resize_session(self, rows: int, cols: int) -> None:
        if self._pty_process is None:
            return
        try:
            self._pty_process.setwinsize(rows, cols)
        except Exception:
            pass

    def _handle_builtin(self, command: str) -> bool:
        parts = shlex.split(command, posix=False)
        if not parts:
            return True

        name = parts[0].lower()
        if name in {"cls", "clear"}:
            self.clear_requested.emit()
            self.command_finished.emit(0)
            return True

        if name == "pwd":
            self.output_received.emit(str(self.cwd), "normal")
            self.command_finished.emit(0)
            return True

        if name == "backend":
            if len(parts) == 1:
                self.output_received.emit(f"Current backend: {self.backend_mode}", "dim")
                self.command_finished.emit(0)
                return True
            requested = parts[1].lower()
            if requested in {"process", "conpty"}:
                if self.supports_backend(requested):
                    self.set_backend_mode(requested)
                    self.output_received.emit(f"Backend switched to {self.backend_mode}", "accent")
                    self.command_finished.emit(0)
                else:
                    self.output_received.emit(f"{requested} backend is not available.", "error")
                    self.command_finished.emit(1)
            else:
                self.output_received.emit("Usage: backend process|conpty", "error")
                self.command_finished.emit(1)
            return True

        if name == "session":
            if len(parts) == 1 or parts[1].lower() == "status":
                state = "on" if self.session_active else "off"
                self.output_received.emit(f"Session mode: {state}", "dim")
                self.command_finished.emit(0)
                return True
            requested = parts[1].lower()
            if requested == "on":
                started = self.start_session()
                if started:
                    self.output_received.emit(f"{self.shell_mode} session started", "accent")
                    self.command_finished.emit(0)
                else:
                    self.output_received.emit("Unable to start session right now.", "error")
                    self.command_finished.emit(1)
                return True
            if requested == "off":
                self.stop_session()
                self.output_received.emit("Session mode: off", "accent")
                self.command_finished.emit(0)
                return True
            self.output_received.emit("Usage: session on|off|status", "error")
            self.command_finished.emit(1)
            return True

        if name == "shell":
            if len(parts) == 1:
                self.output_received.emit(f"Current shell: {self.shell_mode}", "dim")
                self.command_finished.emit(0)
                return True
            requested = parts[1].lower()
            if requested in {"cmd", "powershell", "sh"}:
                if self.session_active:
                    self.stop_session()
                self.shell_mode = requested
                self.shell_changed.emit(self.shell_mode)
                self.output_received.emit(f"Shell switched to {self.shell_mode}", "accent")
                self.command_finished.emit(0)
            else:
                self.output_received.emit("Usage: shell cmd|powershell", "error")
                self.command_finished.emit(1)
            return True

        if name == "cd":
            raw_target = parts[1] if len(parts) > 1 else str(Path.home())
            target = Path(raw_target.replace('"', ""))
            next_dir = (self.cwd / target).resolve() if not target.is_absolute() else target.resolve()
            if next_dir.exists() and next_dir.is_dir():
                self.cwd = next_dir
                self.cwd_changed.emit(str(self.cwd))
                if self.session_active and self.is_running():
                    command_text = f'cd /d "{self.cwd}"\n' if os.name == "nt" and self.shell_mode == "cmd" else f'cd "{self.cwd}"\n'
                    self._write_session(command_text)
                else:
                    self.output_received.emit(str(self.cwd), "dim")
                self.command_finished.emit(0)
            else:
                self.output_received.emit(f"The system cannot find the path specified: {raw_target}", "error")
                self.command_finished.emit(1)
            return True

        return False

    def _read_output(self) -> None:
        self._stdout_buffer += bytes(self.process.readAllStandardOutput())
        text = self._decode_buffer(final=False)
        if text:
            for line in text.splitlines():
                self.output_received.emit(line, "normal")

    def _on_finished(self, exit_code: int, _exit_status) -> None:
        tail = self._decode_buffer(final=True)
        if tail:
            for line in tail.splitlines():
                self.output_received.emit(line, "normal")
        if self.session_active:
            self.session_active = False
            self.session_changed.emit(False)
        self.command_finished.emit(exit_code)

    def _on_error(self, _error) -> None:
        if self.process.error() == QProcess.ProcessError.FailedToStart:
            self.output_received.emit("Failed to start command.", "error")

    def _decode_buffer(self, final: bool) -> str:
        if not self._stdout_buffer:
            return ""

        try:
            text = self._stdout_buffer.decode(self.encoding)
        except UnicodeDecodeError:
            if not final:
                return ""
            text = self._stdout_buffer.decode(self.encoding, errors="replace")

        if final or text.endswith(("\n", "\r")):
            self._stdout_buffer = b""
            return text.rstrip("\r\n")

        lines = text.splitlines()
        if len(lines) <= 1:
            return ""

        tail = lines[-1]
        emitted = text[: len(text) - len(tail)]
        self._stdout_buffer = tail.encode(self.encoding, errors="replace")
        return emitted.rstrip("\r\n")

    def _session_argv(self) -> list[str]:
        if self.shell_mode == "powershell":
            return [
                "powershell.exe",
                "-NoLogo",
                "-NoProfile",
                "-NoExit",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                "function prompt { \"$pwd> \" }",
            ]
        return ["cmd.exe", "/Q", "/K", "prompt", "$P$G"]

    def _write_session(self, text: str) -> None:
        if self._pty_process is not None:
            self._pty_process.write(text.replace("\n", "\r\n"))
            return
        self.process.write(text.encode(self.encoding, errors="replace"))

    def _read_pty_loop(self) -> None:
        proc = self._pty_process
        if proc is None:
            return
        try:
            while proc.isalive():
                chunk = proc.read(4096)
                if not chunk:
                    continue
                self._emit_pty_text(chunk)
        except EOFError:
            pass
        except Exception as exc:
            self.output_received.emit(f"PTY error: {exc}", "error")
        finally:
            self._pty_process = None
            if self.session_active:
                self.session_active = False
                self.session_changed.emit(False)
            self.command_finished.emit(0)

    def _emit_pty_text(self, text: str) -> None:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        self._pty_buffer += normalized
        if "\n" not in self._pty_buffer:
            return
        lines = self._pty_buffer.split("\n")
        self._pty_buffer = lines.pop()
        for line in lines:
            if line:
                self.output_received.emit(line, "normal")
