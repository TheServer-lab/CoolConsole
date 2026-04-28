from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from core.terminal_buffer import TerminalLine


class AnimationManager(QObject):
    typing_finished = pyqtSignal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)
        self._line: TerminalLine | None = None
        self._on_step: Callable[[], None] | None = None
        self._chars_per_tick = 1

    def type_line(
        self,
        line: TerminalLine,
        on_step: Callable[[], None],
        interval_ms: int = 18,
        chars_per_tick: int = 1,
    ) -> None:
        self._line = line
        self._on_step = on_step
        self._chars_per_tick = max(1, chars_per_tick)
        self._timer.start(interval_ms)

    def is_running(self) -> bool:
        return self._timer.isActive()

    def _advance(self) -> None:
        if self._line is None:
            self._timer.stop()
            return

        self._line.revealed = min(len(self._line.text), self._line.revealed + self._chars_per_tick)

        if self._on_step is not None:
            self._on_step()

        if self._line.done:
            self._timer.stop()
            self.typing_finished.emit()
