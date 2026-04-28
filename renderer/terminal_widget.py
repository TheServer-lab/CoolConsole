from __future__ import annotations

import configparser
import random
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtGui import QColor, QFontMetricsF, QLinearGradient, QPainter, QPainterPath, QPen
from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollBar,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from core.animation_manager import AnimationManager
from core.command_runner import CommandRunner
from core.terminal_buffer import TerminalBuffer, TerminalLine
from effects.glow import paint_panel_glow
from effects.typing import suggested_typing_speed
from renderer.cursor import CursorController
from renderer.text_renderer import TextRenderer


@dataclass
class Theme:
    name: str
    background: QColor
    foreground: QColor
    cursor: QColor
    selection: QColor
    chrome: QColor
    chrome_text: QColor
    accent: QColor
    font: str
    font_size: int
    smooth_cursor: bool
    glow: bool
    crt: bool
    gradient: str = "diagonal"
    corner_radius: int = 18
    matrix: bool = False
    acrylic: bool = False
    shell_mode: str = "cmd"
    typing_animation: bool = True
    backend_mode: str = "process"


ACCENT_PRESETS = {
    "Neon Green": "#0cff9b",
    "Ice Blue": "#5af4ff",
    "Amber": "#ffb347",
    "Hacker Red": "#ff4d67",
    "Synth Pink": "#ff4fd8",
}

GRADIENT_PRESETS = {
    "Diagonal": "diagonal",
    "Vertical": "vertical",
    "Horizontal": "horizontal",
}

FONT_PRESETS = [
    "Consolas",
    "Cascadia Code",
    "JetBrains Mono",
    "Fira Code",
    "Hack",
    "Courier New",
]

SHELL_PRESETS = {
    "Command Prompt": "cmd",
    "PowerShell": "powershell",
}

BACKEND_PRESETS = {
    "Process": "process",
    "ConPTY": "conpty",
}


class CoolConsoleWindow(QWidget):
    def __init__(self, root: Path) -> None:
        super().__init__()
        self.root = root
        self.setWindowTitle("CoolConsole")
        self.setMinimumSize(880, 560)
        self.resize(1120, 700)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAcceptDrops(True)

        self.theme = self._load_theme()
        self.buffer = TerminalBuffer()
        self.text_renderer = TextRenderer(self.theme.font, self.theme.font_size)
        self.cursor = CursorController(self)
        self.cursor._timer.timeout.connect(self.update)
        self.animations = AnimationManager(self)
        self.animations.typing_finished.connect(self._on_typing_finished)
        self.command_runner = CommandRunner(root, self)
        self.command_runner.shell_mode = self.theme.shell_mode
        self.command_runner.set_backend_mode(self.theme.backend_mode)
        self.theme.backend_mode = self.command_runner.backend_mode
        self.command_runner.output_received.connect(self._append_output)
        self.command_runner.command_finished.connect(self._on_command_finished)
        self.command_runner.cwd_changed.connect(self._on_cwd_changed)
        self.command_runner.clear_requested.connect(self._clear_terminal)
        self.command_runner.shell_changed.connect(self._on_shell_changed)
        self.command_runner.session_changed.connect(self._on_session_changed)
        self.command_runner.backend_changed.connect(self._on_backend_changed)

        self._drag_offset: QPoint | None = None
        self._title_bar_height = 46
        self._padding = 28
        self._title_button_radius = 6.0
        self._title_button_spacing = 18.0
        self._github_url = "https://github.com/TheServer-lab/CoolConsole"
        self._current_input = ""
        self._input_cursor = 0
        self._history: list[str] = []
        self._history_index = -1
        self._auto_scroll_target = 0.0
        self._scroll_velocity = 0.0
        self._typing_queue: list[tuple[str, str, str]] = []
        self._settings_open = False
        self._drop_highlight = False
        self._idle_ticks = 0
        self._matrix_columns: list[float] = []
        self._matrix_speeds: list[float] = []
        self._progress_lines: list[TerminalLine] = []
        self._crt_flicker = 0.0
        self._selection_anchor: tuple[int, int] | None = None
        self._selection_cursor: tuple[int, int] | None = None
        self._is_selecting = False
        self._matrix_hold_ticks = 0
        self._syncing_scrollbar = False

        self._intro_lines = [
            "Initializing CoolConsole...",
            "Loading renderer...",
            "Loading effects...",
            f"Applying theme {self.theme.name}...",
            "Ready.",
            "",
            "\u2714 System Ready",
            "\U0001F525 Rendering Engine Online",
            "\U0001F4E6 Loading Assets...",
            "Unicode channel: \u4F60\u597D | \u041F\u0440\u0438\u0432\u0435\u0442 | \u0645\u0631\u062D\u0628\u0627",
            "Emoji lane: \U0001F600 \U0001F680 \u2728",
            "",
            "Type a command and press Enter.",
            "Built-ins: cd, pwd, clear, cls, settings, coolconsole, progressdemo, shell, session, backend",
        ]

        self._scroll_timer = QTimer(self)
        self._scroll_timer.timeout.connect(self._tick_scroll)
        self._scroll_timer.start(16)

        self._effects_timer = QTimer(self)
        self._effects_timer.timeout.connect(self._tick_effects)
        self._effects_timer.start(33)

        self._scrollbar = QScrollBar(Qt.Orientation.Vertical, self)
        self._scrollbar.valueChanged.connect(self._on_scrollbar_changed)
        self._scrollbar.setStyleSheet(
            "QScrollBar:vertical { background: rgba(0,0,0,70); width: 12px; margin: 0; border-radius: 6px; }"
            "QScrollBar::handle:vertical { background: rgba(12,255,155,150); min-height: 30px; border-radius: 6px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }"
        )

        self._build_settings_panel()
        self._refresh_settings_ui()
        self._refresh_translucency()

    def _load_theme(self) -> Theme:
        profile = configparser.ConfigParser()
        profile.read(self.root / "profiles" / "default.profile", encoding="utf-8")
        theme_name = profile.get("profile", "theme", fallback="cybergreen.theme")

        parser = configparser.ConfigParser()
        parser.read(self.root / "themes" / theme_name, encoding="utf-8")
        section = parser["theme"]

        return Theme(
            name=section.get("name", "CyberGreen"),
            background=QColor(section.get("background", "#050505")),
            foreground=QColor(section.get("foreground", "#00ff88")),
            cursor=QColor(section.get("cursor", "#00ffaa")),
            selection=QColor(section.get("selection", "#114422")),
            chrome=QColor(section.get("chrome", "#0d1117")),
            chrome_text=QColor(section.get("chrome_text", "#d8ffe9")),
            accent=QColor(profile.get("profile", "accent", fallback=section.get("accent", "#0cff9b"))),
            font=profile.get("profile", "font", fallback=section.get("font", "Consolas")),
            font_size=profile.getint("profile", "font_size", fallback=section.getint("font_size", 14)),
            smooth_cursor=section.getboolean("smooth_cursor", True),
            glow=profile.getboolean("profile", "glow", fallback=section.getboolean("glow", True)),
            crt=profile.getboolean("profile", "crt", fallback=section.getboolean("crt", False)),
            gradient=profile.get("profile", "gradient", fallback="diagonal"),
            corner_radius=profile.getint("profile", "corner_radius", fallback=18),
            matrix=profile.getboolean("profile", "matrix", fallback=False),
            acrylic=profile.getboolean("profile", "acrylic", fallback=False),
            shell_mode=profile.get("profile", "shell", fallback="cmd"),
            typing_animation=profile.getboolean("profile", "typing_animation", fallback=True),
            backend_mode=profile.get("profile", "backend", fallback=("conpty" if self.command_runner.supports_backend("conpty") else "process")) if hasattr(self, "command_runner") else profile.get("profile", "backend", fallback="process"),
        )

    def _save_profile(self) -> None:
        theme_slug = f"{self.theme.name.lower()}.theme"
        profile = configparser.ConfigParser()
        profile["profile"] = {
            "theme": theme_slug,
            "startup_sequence": "default",
            "accent": self.theme.accent.name(),
            "gradient": self.theme.gradient,
            "corner_radius": str(self.theme.corner_radius),
            "font": self.theme.font,
            "font_size": str(self.theme.font_size),
            "glow": str(self.theme.glow).lower(),
            "crt": str(self.theme.crt).lower(),
            "matrix": str(self.theme.matrix).lower(),
            "acrylic": str(self.theme.acrylic).lower(),
            "shell": self.theme.shell_mode,
            "typing_animation": str(self.theme.typing_animation).lower(),
            "backend": self.theme.backend_mode,
        }
        with (self.root / "profiles" / "default.profile").open("w", encoding="utf-8") as handle:
            profile.write(handle)

    def _build_settings_panel(self) -> None:
        self.settings_panel = QFrame(self)
        self.settings_panel.hide()
        self.settings_panel.setStyleSheet(
            "QFrame { background: rgba(10, 16, 20, 240); border: 1px solid #2d434d; border-radius: 10px; }"
            "QLabel { color: #d8ffe9; }"
            "QComboBox, QPushButton { background: #10181d; color: #d8ffe9; border: 1px solid #2f4650; border-radius: 6px; padding: 6px; }"
            "QCheckBox { color: #d8ffe9; }"
        )
        layout = QVBoxLayout(self.settings_panel)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        layout.addWidget(QLabel("Visual Settings", self.settings_panel))

        self.theme_combo = QComboBox(self.settings_panel)
        for theme_file in sorted((self.root / "themes").glob("*.theme")):
            self.theme_combo.addItem(theme_file.stem, theme_file.name)
        self.theme_combo.currentIndexChanged.connect(self._apply_theme_from_settings)
        layout.addWidget(self._make_setting_row("Theme", self.theme_combo))

        self.accent_combo = QComboBox(self.settings_panel)
        for label, value in ACCENT_PRESETS.items():
            self.accent_combo.addItem(label, value)
        self.accent_combo.currentIndexChanged.connect(self._apply_settings)
        layout.addWidget(self._make_setting_row("Accent", self.accent_combo))

        self.gradient_combo = QComboBox(self.settings_panel)
        for label, value in GRADIENT_PRESETS.items():
            self.gradient_combo.addItem(label, value)
        self.gradient_combo.currentIndexChanged.connect(self._apply_settings)
        layout.addWidget(self._make_setting_row("Gradient", self.gradient_combo))

        self.font_combo = QComboBox(self.settings_panel)
        for family in FONT_PRESETS:
            self.font_combo.addItem(family, family)
        self.font_combo.currentIndexChanged.connect(self._apply_settings)
        layout.addWidget(self._make_setting_row("Font", self.font_combo))

        self.shell_combo = QComboBox(self.settings_panel)
        for label, value in SHELL_PRESETS.items():
            self.shell_combo.addItem(label, value)
        self.shell_combo.currentIndexChanged.connect(self._apply_settings)
        layout.addWidget(self._make_setting_row("Shell", self.shell_combo))

        self.backend_combo = QComboBox(self.settings_panel)
        for label, value in BACKEND_PRESETS.items():
            self.backend_combo.addItem(label, value)
            if not self.command_runner.supports_backend(value):
                index = self.backend_combo.findData(value)
                self.backend_combo.setItemData(index, 0, Qt.ItemDataRole.UserRole - 1)
        self.backend_combo.currentIndexChanged.connect(self._apply_settings)
        layout.addWidget(self._make_setting_row("Backend", self.backend_combo))

        self.radius_slider = QSlider(Qt.Orientation.Horizontal, self.settings_panel)
        self.radius_slider.setRange(6, 32)
        self.radius_slider.valueChanged.connect(self._apply_settings)
        layout.addWidget(self._make_setting_row("Shape", self.radius_slider))

        self.font_size_slider = QSlider(Qt.Orientation.Horizontal, self.settings_panel)
        self.font_size_slider.setRange(11, 24)
        self.font_size_slider.valueChanged.connect(self._apply_settings)
        layout.addWidget(self._make_setting_row("Font Size", self.font_size_slider))

        self.glow_checkbox = QCheckBox("Glow", self.settings_panel)
        self.glow_checkbox.stateChanged.connect(self._apply_settings)
        layout.addWidget(self.glow_checkbox)

        self.typing_checkbox = QCheckBox("Typing Animation", self.settings_panel)
        self.typing_checkbox.stateChanged.connect(self._apply_settings)
        layout.addWidget(self.typing_checkbox)

        self.crt_checkbox = QCheckBox("CRT Overlay", self.settings_panel)
        self.crt_checkbox.stateChanged.connect(self._apply_settings)
        layout.addWidget(self.crt_checkbox)

        self.matrix_checkbox = QCheckBox("Matrix Ambient", self.settings_panel)
        self.matrix_checkbox.stateChanged.connect(self._apply_settings)
        layout.addWidget(self.matrix_checkbox)

        self.acrylic_checkbox = QCheckBox("Acrylic Mode", self.settings_panel)
        self.acrylic_checkbox.stateChanged.connect(self._apply_settings)
        layout.addWidget(self.acrylic_checkbox)

        close_button = QPushButton("Close", self.settings_panel)
        close_button.clicked.connect(self.toggle_settings)
        layout.addWidget(close_button)

    def _make_setting_row(self, label_text: str, control: QWidget) -> QWidget:
        row = QWidget(self.settings_panel)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(10)
        label = QLabel(label_text, row)
        label.setFixedWidth(76)
        row_layout.addWidget(label)
        row_layout.addWidget(control, 1)
        return row

    def _refresh_settings_ui(self) -> None:
        self._set_combo_value(self.theme_combo, f"{self.theme.name.lower()}.theme")
        self._set_combo_value(self.accent_combo, self.theme.accent.name())
        self._set_combo_value(self.gradient_combo, self.theme.gradient)
        self._set_combo_value(self.font_combo, self.theme.font)
        self._set_combo_value(self.shell_combo, self.theme.shell_mode)
        self._set_combo_value(self.backend_combo, self.theme.backend_mode)
        self.radius_slider.setValue(self.theme.corner_radius)
        self.font_size_slider.setValue(self.theme.font_size)
        self.glow_checkbox.setChecked(self.theme.glow)
        self.typing_checkbox.setChecked(self.theme.typing_animation)
        self.crt_checkbox.setChecked(self.theme.crt)
        self.matrix_checkbox.setChecked(self.theme.matrix)
        self.acrylic_checkbox.setChecked(self.theme.acrylic)
        self._place_settings_panel()

    def _set_combo_value(self, combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        if index >= 0 and combo.currentIndex() != index:
            combo.setCurrentIndex(index)

    def _place_settings_panel(self) -> None:
        shell = self._shell_rect()
        self.settings_panel.setGeometry(int(shell.right() - 338), int(shell.top() + self._title_bar_height + 14), 320, 490)

    def _apply_theme_from_settings(self) -> None:
        theme_name = self.theme_combo.currentData()
        if not theme_name:
            return
        parser = configparser.ConfigParser()
        parser.read(self.root / "themes" / theme_name, encoding="utf-8")
        section = parser["theme"]
        self.theme.name = section.get("name", self.theme.name)
        self.theme.background = QColor(section.get("background", self.theme.background.name()))
        self.theme.foreground = QColor(section.get("foreground", self.theme.foreground.name()))
        self.theme.cursor = QColor(section.get("cursor", self.theme.cursor.name()))
        self.theme.selection = QColor(section.get("selection", self.theme.selection.name()))
        self.theme.chrome = QColor(section.get("chrome", self.theme.chrome.name()))
        self.theme.chrome_text = QColor(section.get("chrome_text", self.theme.chrome_text.name()))
        self.theme.smooth_cursor = section.getboolean("smooth_cursor", self.theme.smooth_cursor)
        self._apply_settings()

    def _apply_settings(self) -> None:
        accent_value = self.accent_combo.currentData()
        font_value = self.font_combo.currentData()
        gradient_value = self.gradient_combo.currentData()
        shell_value = self.shell_combo.currentData()
        backend_value = self.backend_combo.currentData()
        if accent_value:
            self.theme.accent = QColor(accent_value)
        if font_value:
            self.theme.font = font_value
        if gradient_value:
            self.theme.gradient = gradient_value
        if shell_value:
            self.theme.shell_mode = shell_value
            self.command_runner.shell_mode = shell_value
        if backend_value and self.command_runner.supports_backend(backend_value):
            self.theme.backend_mode = backend_value
            self.command_runner.set_backend_mode(backend_value)
        self.theme.font_size = self.font_size_slider.value()
        self.theme.corner_radius = self.radius_slider.value()
        self.theme.glow = self.glow_checkbox.isChecked()
        self.theme.typing_animation = self.typing_checkbox.isChecked()
        self.theme.crt = self.crt_checkbox.isChecked()
        self.theme.matrix = self.matrix_checkbox.isChecked()
        self.theme.acrylic = self.acrylic_checkbox.isChecked()
        self.text_renderer.set_font(self.theme.font, self.theme.font_size)
        self._refresh_translucency()
        self._save_profile()
        self.update()

    def _refresh_translucency(self) -> None:
        if self.theme.acrylic:
            self.setWindowOpacity(0.94)
        else:
            self.setWindowOpacity(1.0)

    def toggle_settings(self) -> None:
        self._settings_open = not self._settings_open
        self.settings_panel.setVisible(self._settings_open)
        self._place_settings_panel()
        self.update()

    def _play_intro_sequence(self) -> None:
        if self.animations.is_running() and self.theme.typing_animation:
            return
        self._clear_terminal()
        self._typing_queue.clear()
        for text in self._intro_lines:
            style = "accent" if "Ready" in text or text.startswith("\u2714") else "normal"
            self._typing_queue.append((text, style, "text"))
        self._animate_next_output()

    def _start_progress_demo(self) -> None:
        self._append_output("Launching cinematic progress demo...", "accent")
        steps = [
            ("Resolving packages", 0.25),
            ("Installing modules", 0.58),
            ("Compiling shaders", 0.81),
            ("Finalizing build", 1.0),
        ]
        for label, target in steps:
            line = self.buffer.append_line(
                "",
                style="progress",
                revealed=0,
                kind="progress",
                progress=0.0,
                progress_target=target,
                progress_label=label,
            )
            self._progress_lines.append(line)
        self._on_line_changed()

    def _animate_next_output(self) -> None:
        if self.animations.is_running() or not self._typing_queue:
            return
        text, style, kind = self._typing_queue.pop(0)
        revealed = 0 if self.theme.typing_animation else len(text)
        line = self.buffer.append_line(text=text, style=style, revealed=revealed, kind=kind)
        if not self.theme.typing_animation:
            self._on_line_changed()
            QTimer.singleShot(0, self._animate_next_output)
            return
        if not text:
            line.revealed = 0
            self._on_line_changed()
            QTimer.singleShot(40, self._animate_next_output)
            return
        interval, chars_per_tick = suggested_typing_speed(text)
        self.animations.type_line(line, self._on_line_changed, interval, chars_per_tick)

    def _on_typing_finished(self) -> None:
        QTimer.singleShot(30, self._animate_next_output)

    def _tick_effects(self) -> None:
        self._idle_ticks += 1
        self._crt_flicker = random.uniform(0.01, 0.06) if self.theme.crt else 0.0
        self._matrix_hold_ticks = max(0, self._matrix_hold_ticks - 1)

        active_progress = []
        changed = False
        for line in self._progress_lines:
            if line.progress < line.progress_target:
                line.progress = min(line.progress_target, line.progress + 0.018)
                changed = True
                active_progress.append(line)
            elif line.progress < 1.0:
                active_progress.append(line)
        self._progress_lines = active_progress

        self._ensure_matrix_columns()
        matrix_on = self._matrix_visible()
        if matrix_on:
            self._advance_matrix()

        if changed or matrix_on or self.theme.crt:
            self.update()

    def _ensure_matrix_columns(self) -> None:
        term_rect = self._terminal_rect()
        count = max(8, int(term_rect.width() // max(12.0, self.text_renderer.text_width("0"))))
        current = len(self._matrix_columns)
        if current == count:
            return
        if current > count:
            # Shrink: just drop columns from the end, keep the rest running.
            self._matrix_columns = self._matrix_columns[:count]
            self._matrix_speeds = self._matrix_speeds[:count]
        else:
            # Grow: append new columns starting above the visible area so they
            # rain in naturally rather than popping in mid-screen.
            for _ in range(count - current):
                self._matrix_columns.append(random.uniform(-term_rect.height(), 0.0))
                self._matrix_speeds.append(random.uniform(3.0, 10.0))

    def _advance_matrix(self) -> None:
        term_rect = self._terminal_rect()
        for index, value in enumerate(self._matrix_columns):
            next_value = value + self._matrix_speeds[index]
            if next_value > term_rect.height() + 60:
                next_value = random.uniform(-term_rect.height() * 0.8, -20.0)
            self._matrix_columns[index] = next_value

    def _on_line_changed(self) -> None:
        self._auto_scroll_target = max(0.0, self._content_height() - self._terminal_rect().height())
        self._sync_scrollbar()
        self.update()

    def _content_height(self) -> float:
        wrap_width = max(40.0, self._terminal_rect().width())
        visual_rows = 0
        for line in self.buffer.lines:
            if line.kind == "progress":
                visual_rows += 1
            else:
                visual_rows += max(1, len(self.text_renderer.wrap_line(line.visible_text, wrap_width)))
        # +1 for the prompt line (also possibly multi-row, but one is a safe min)
        prompt_text = f"{self._prompt_prefix()} {self._current_input}"
        visual_rows += max(1, len(self.text_renderer.wrap_line(prompt_text, wrap_width)))
        return visual_rows * (self.text_renderer.line_height + 2) + self._padding * 2

    def _tick_scroll(self) -> None:
        delta = self._auto_scroll_target - self.buffer.scroll_offset
        if abs(delta) < 0.5:
            self.buffer.scroll_offset = self._auto_scroll_target
            self._sync_scrollbar()
            return
        self._scroll_velocity = delta * 0.18
        self.buffer.scroll_offset += self._scroll_velocity
        self._sync_scrollbar()
        self.update()

    def _terminal_rect(self) -> QRectF:
        scrollbar_w = 14
        return QRectF(
            self._padding,
            self._title_bar_height + 18,
            self.width() - self._padding * 2 - scrollbar_w,
            self.height() - self._title_bar_height - self._padding - 24,
        )

    def _shell_rect(self) -> QRectF:
        rect = self.rect()
        return QRectF(10, 10, rect.width() - 20, rect.height() - 20)

    def _title_rect(self) -> QRectF:
        shell_rect = self._shell_rect()
        return QRectF(shell_rect.left(), shell_rect.top(), shell_rect.width(), self._title_bar_height)

    def _title_button_centers(self) -> list[QPointF]:
        title_rect = self._title_rect()
        start_x = title_rect.left() + 20
        center_y = title_rect.top() + (title_rect.height() / 2)
        return [QPointF(start_x + index * self._title_button_spacing, center_y) for index in range(3)]

    def _title_button_hit_rects(self) -> list[QRectF]:
        hit_size = 18.0
        half = hit_size / 2
        return [QRectF(center.x() - half, center.y() - half, hit_size, hit_size) for center in self._title_button_centers()]

    def _github_link_rect(self) -> QRectF:
        title_rect = self._title_rect()
        left_bound = title_rect.left() + 220.0
        right_bound = title_rect.right() - 230.0
        return QRectF(left_bound, title_rect.top(), max(120.0, right_bound - left_bound), title_rect.height())

    def _title_bar_action_at(self, pos: QPointF) -> str | None:
        actions = ["close", "minimize", "maximize"]
        for action, rect in zip(actions, self._title_button_hit_rects()):
            if rect.contains(pos):
                return action
        return None

    def _handle_title_bar_action(self, action: str) -> None:
        if action == "close":
            self.close()
        elif action == "minimize":
            self.showMinimized()
        elif action == "maximize":
            if self.isMaximized():
                self.showNormal()
            else:
                self.showMaximized()

    def cycle_theme(self) -> None:
        theme_files = sorted((self.root / "themes").glob("*.theme"))
        current = f"{self.theme.name.lower()}.theme"
        names = [path.name for path in theme_files]
        next_theme = theme_files[0].name if current not in names else theme_files[(names.index(current) + 1) % len(theme_files)].name
        self._set_combo_value(self.theme_combo, next_theme)
        self._apply_theme_from_settings()

    def _prompt_prefix(self) -> str:
        return f"{self.command_runner.cwd.name or str(self.command_runner.cwd)}>"

    def _status_text(self) -> str:
        cwd_text = str(self.command_runner.cwd)
        session_text = "session" if self.command_runner.session_active else "oneshot"
        return f"{self.theme.shell_mode}  |  {self.theme.backend_mode}  |  {session_text}  |  {cwd_text}"

    def _input_locked(self) -> bool:
        return self.command_runner.is_running() and not self.command_runner.session_active

    def _matrix_visible(self) -> bool:
        return self.theme.matrix or self._matrix_hold_ticks > 0 or (self._idle_ticks > 180 and not self.command_runner.is_running())

    def _mark_activity(self) -> None:
        self._idle_ticks = 0
        self._matrix_hold_ticks = 300

    def _sync_scrollbar(self) -> None:
        max_scroll = max(0, int(round(self._content_height() - self._terminal_rect().height())))
        self._syncing_scrollbar = True
        self._scrollbar.setRange(0, max_scroll)
        self._scrollbar.setPageStep(max(1, int(self._terminal_rect().height())))
        self._scrollbar.setValue(int(round(self.buffer.scroll_offset)))
        self._syncing_scrollbar = False

    def _on_scrollbar_changed(self, value: int) -> None:
        if self._syncing_scrollbar:
            return
        self._auto_scroll_target = float(value)
        self.buffer.scroll_offset = float(value)
        self.update()

    def _insert_text_at_cursor(self, text: str) -> None:
        if not text:
            return
        self._current_input = (
            self._current_input[: self._input_cursor]
            + text
            + self._current_input[self._input_cursor :]
        )
        self._input_cursor += len(text)

    def _delete_backward(self) -> None:
        if self._input_cursor <= 0:
            return
        self._current_input = (
            self._current_input[: self._input_cursor - 1]
            + self._current_input[self._input_cursor :]
        )
        self._input_cursor -= 1

    def _delete_forward(self) -> None:
        if self._input_cursor >= len(self._current_input):
            return
        self._current_input = (
            self._current_input[: self._input_cursor]
            + self._current_input[self._input_cursor + 1 :]
        )

    def _move_cursor_word_left(self) -> None:
        if self._input_cursor <= 0:
            return
        pos = self._input_cursor
        while pos > 0 and self._current_input[pos - 1].isspace():
            pos -= 1
        while pos > 0 and not self._current_input[pos - 1].isspace():
            pos -= 1
        self._input_cursor = pos

    def _move_cursor_word_right(self) -> None:
        pos = self._input_cursor
        length = len(self._current_input)
        while pos < length and self._current_input[pos].isspace():
            pos += 1
        while pos < length and not self._current_input[pos].isspace():
            pos += 1
        self._input_cursor = pos

    def _delete_word_backward(self) -> None:
        if self._input_cursor <= 0:
            return
        start = self._input_cursor
        while start > 0 and self._current_input[start - 1].isspace():
            start -= 1
        while start > 0 and not self._current_input[start - 1].isspace():
            start -= 1
        self._current_input = self._current_input[:start] + self._current_input[self._input_cursor :]
        self._input_cursor = start

    def _delete_word_forward(self) -> None:
        if self._input_cursor >= len(self._current_input):
            return
        end = self._input_cursor
        length = len(self._current_input)
        while end < length and self._current_input[end].isspace():
            end += 1
        while end < length and not self._current_input[end].isspace():
            end += 1
        self._current_input = self._current_input[: self._input_cursor] + self._current_input[end:]

    def _paste_from_clipboard(self) -> None:
        text = QApplication.clipboard().text()
        if not text:
            return
        normalized = text.replace("\r\n", " ").replace("\n", " ")
        self._clear_selection()
        self._insert_text_at_cursor(normalized)
        self.update()

    def _progress_display_text(self, line: TerminalLine) -> str:
        blocks_total = 16
        filled = int(round(blocks_total * line.progress))
        return "[" + ("\u2588" * filled) + ("\u2591" * (blocks_total - filled)) + f"] {line.progress_label}"

    def _build_render_rows(self) -> list[dict]:
        term_rect = self._terminal_rect()
        wrap_width = max(40.0, term_rect.width())
        rows: list[dict] = []
        y = term_rect.top() + self._padding - self.buffer.scroll_offset
        for line in self.buffer.lines:
            line_height = self.text_renderer.line_height + (10 if line.kind == "progress" else 2)
            text = self._progress_display_text(line) if line.kind == "progress" else line.visible_text
            # Progress bars are never wrapped; regular text is wrapped to the
            # terminal width so neither the display nor the cursor escapes the
            # right edge.
            if line.kind == "progress":
                segments = [text]
            else:
                segments = self.text_renderer.wrap_line(text, wrap_width)
            for segment in segments:
                rows.append(
                    {
                        "text": segment,
                        "style": "progress_text" if line.kind == "progress" else line.style,
                        "y": y,
                        "line_height": line_height,
                        "kind": line.kind,
                        "line": line,
                    }
                )
                y += line_height
        # Prompt row — also wrapped so the active-input line behaves correctly.
        prompt_text = f"{self._prompt_prefix()} {self._current_input}"
        prompt_segments = self.text_renderer.wrap_line(prompt_text, wrap_width)
        y += 10  # small gap before the prompt
        for segment in prompt_segments:
            rows.append(
                {
                    "text": segment,
                    "style": "prompt_active",
                    "y": y,
                    "line_height": self.text_renderer.line_height,
                    "kind": "prompt",
                    "line": None,
                }
            )
            y += self.text_renderer.line_height
        return rows

    def _selection_bounds(self) -> tuple[tuple[int, int], tuple[int, int]] | None:
        if self._selection_anchor is None or self._selection_cursor is None:
            return None
        start = self._selection_anchor
        end = self._selection_cursor
        return (start, end) if start <= end else (end, start)

    def _has_selection(self) -> bool:
        bounds = self._selection_bounds()
        return bounds is not None and bounds[0] != bounds[1]

    def _clear_selection(self) -> None:
        self._selection_anchor = None
        self._selection_cursor = None
        self._is_selecting = False

    def _copy_selection(self) -> bool:
        text = self._selected_text()
        if not text:
            return False
        QApplication.clipboard().setText(text)
        return True

    def _selected_text(self) -> str:
        bounds = self._selection_bounds()
        if bounds is None:
            return ""
        rows = self._build_render_rows()
        if not rows:
            return ""
        (start_row, start_col), (end_row, end_col) = bounds
        collected: list[str] = []
        for row_index in range(start_row, min(end_row + 1, len(rows))):
            row_text = rows[row_index]["text"]
            left = start_col if row_index == start_row else 0
            right = end_col if row_index == end_row else len(row_text)
            left = max(0, min(left, len(row_text)))
            right = max(0, min(right, len(row_text)))
            collected.append(row_text[left:right])
        return "\n".join(collected)

    def _selection_for_row(self, row_index: int, row_text: str) -> tuple[int, int] | None:
        bounds = self._selection_bounds()
        if bounds is None:
            return None
        (start_row, start_col), (end_row, end_col) = bounds
        if row_index < start_row or row_index > end_row:
            return None
        left = start_col if row_index == start_row else 0
        right = end_col if row_index == end_row else len(row_text)
        left = max(0, min(left, len(row_text)))
        right = max(0, min(right, len(row_text)))
        if left == right:
            return None
        return left, right

    def _hit_test_text_position(self, pos: QPointF) -> tuple[int, int] | None:
        rows = self._build_render_rows()
        if not rows:
            return None
        term_rect = self._terminal_rect()
        clamped_x = max(term_rect.left(), min(pos.x(), term_rect.right()))
        clamped_y = pos.y()
        for row_index, row in enumerate(rows):
            row_top = row["y"]
            row_bottom = row_top + row["line_height"]
            if row_top <= clamped_y <= row_bottom:
                text = row["text"]
                char_index = 0
                for index in range(len(text) + 1):
                    width = self.text_renderer.text_width(text[:index])
                    if term_rect.left() + width >= clamped_x:
                        char_index = max(0, index - 1)
                        break
                    char_index = index
                if clamped_x <= term_rect.left():
                    char_index = 0
                elif clamped_x >= term_rect.left() + self.text_renderer.text_width(text):
                    char_index = len(text)
                else:
                    for index in range(len(text) + 1):
                        width = self.text_renderer.text_width(text[:index])
                        if term_rect.left() + width >= clamped_x:
                            char_index = index
                            break
                return row_index, char_index
        if clamped_y < rows[0]["y"]:
            return 0, 0
        last_index = len(rows) - 1
        return last_index, len(rows[last_index]["text"])

    def _append_output(self, text: str, style: str = "normal") -> None:
        self._mark_activity()
        for part in text.splitlines() or [""]:
            self._typing_queue.append((part, style, "text"))
        self._animate_next_output()

    def _on_command_finished(self, exit_code: int) -> None:
        if exit_code != 0:
            self._append_output(f"[exit {exit_code}]", "error")
        self.update()

    def _on_cwd_changed(self, _cwd: str) -> None:
        self.update()

    def _on_shell_changed(self, shell_name: str) -> None:
        self.theme.shell_mode = shell_name
        self._set_combo_value(self.shell_combo, shell_name)
        self._save_profile()
        self.update()

    def _on_session_changed(self, _enabled: bool) -> None:
        self.update()

    def _on_backend_changed(self, backend_name: str) -> None:
        self.theme.backend_mode = backend_name
        self._set_combo_value(self.backend_combo, backend_name)
        self._save_profile()
        self.update()

    def _clear_terminal(self) -> None:
        self.buffer.clear()
        self._progress_lines.clear()
        self._clear_selection()
        self._auto_scroll_target = 0.0
        self._sync_scrollbar()
        self.update()

    def _submit_current_command(self) -> None:
        if self._input_locked():
            return
        self._mark_activity()
        command = self._current_input.strip()
        prompt = self._prompt_prefix()
        prompt_line = f"{prompt} {self._current_input}"
        self.buffer.append_line(prompt_line, style="prompt", revealed=len(prompt_line))
        self._current_input = ""
        self._input_cursor = 0
        self._history_index = -1
        if not command:
            self._on_line_changed()
            return
        self._history.append(command)
        lowered = command.lower()
        if lowered == "coolconsole":
            self._play_intro_sequence()
        elif lowered == "settings":
            self.toggle_settings()
        elif lowered == "progressdemo":
            self._start_progress_demo()
        else:
            self.command_runner.run_command(command)
        self._on_line_changed()

    def _history_move(self, direction: int) -> None:
        if not self._history:
            return
        if self._history_index == -1:
            self._history_index = len(self._history)
        self._history_index = max(0, min(len(self._history), self._history_index + direction))
        self._current_input = "" if self._history_index == len(self._history) else self._history[self._history_index]
        self._input_cursor = len(self._current_input)
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        self._paint_window_shell(painter)
        self._paint_terminal(painter)
        if self.theme.crt:
            self._paint_crt_overlay(painter)

    def _paint_window_shell(self, painter: QPainter) -> None:
        shell_rect = self._shell_rect()
        path = QPainterPath()
        radius = float(self.theme.corner_radius)
        path.addRoundedRect(shell_rect, radius, radius)

        backdrop_alpha = 120 if self.theme.acrylic else 150
        painter.fillPath(path, QColor(0, 0, 0, backdrop_alpha))

        if self.theme.gradient == "vertical":
            panel = QLinearGradient(shell_rect.left(), shell_rect.top(), shell_rect.left(), shell_rect.bottom())
        elif self.theme.gradient == "horizontal":
            panel = QLinearGradient(shell_rect.left(), shell_rect.top(), shell_rect.right(), shell_rect.top())
        else:
            panel = QLinearGradient(shell_rect.topLeft(), shell_rect.bottomRight())
        panel.setColorAt(0.0, self.theme.background.lighter(118))
        panel.setColorAt(0.45, self.theme.background)
        panel.setColorAt(1.0, self.theme.background.darker(135))
        painter.fillPath(path, panel)

        border = QPen(self.theme.accent, 1.2)
        border.setCosmetic(True)
        painter.setPen(border)
        painter.drawPath(path)

        if self.theme.glow or self.theme.acrylic:
            paint_panel_glow(painter, QPointF(shell_rect.right() - 120, shell_rect.top() + 90), 180, self.theme.accent, 38 if self.theme.acrylic else 28)

        title_rect = self._title_rect()
        title_fill = QColor(self.theme.chrome)
        if self.theme.acrylic:
            title_fill.setAlpha(210)
        painter.fillRect(title_rect, title_fill)
        painter.setPen(self.theme.chrome_text)
        painter.setFont(self.text_renderer.font)
        title_text_rect = QRectF(title_rect.left() + 72, title_rect.top(), max(0.0, title_rect.width() - 310), title_rect.height())
        painter.drawText(title_text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "CoolConsole")
        github_rect = self._github_link_rect()
        github_color = QColor(self.theme.accent)
        github_color.setAlpha(220)
        painter.setPen(github_color)
        github_font = self.text_renderer.font
        github_font.setPointSize(max(9, self.theme.font_size - 2))
        painter.setFont(github_font)
        painter.drawText(
            github_rect,
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
            "github.com/TheServer-lab/CoolConsole",
        )
        painter.setFont(self.text_renderer.font)
        painter.setPen(self.theme.chrome_text)
        painter.drawText(
            title_rect.adjusted(0, 0, -18, 0),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            f"{self.theme.name}  {self.theme.shell_mode}  [F2] [F3]",
        )

        for center, color in zip(self._title_button_centers(), (QColor("#ff5f57"), QColor("#febc2e"), QColor("#28c840"))):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(center, self._title_button_radius, self._title_button_radius)

    def _paint_terminal(self, painter: QPainter) -> None:
        term_rect = self._terminal_rect()
        painter.save()
        painter.setClipRect(term_rect)

        if self._matrix_visible():
            self._paint_matrix_overlay(painter, term_rect)

        rows = self._build_render_rows()
        for row_index, row in enumerate(rows):
            y = row["y"]
            line_height = row["line_height"]
            if y + line_height < term_rect.top():
                continue
            if y > term_rect.bottom():
                break
            line = row["line"]
            if row["kind"] == "progress" and line is not None:
                self._paint_progress_line(painter, term_rect, y, line, row_index, row["text"])
            else:
                self._paint_text_line(painter, term_rect, y, row["text"], row["style"], row_index)

        prompt_rows = [r for r in rows if r["kind"] == "prompt"]
        if self.cursor.visible and not self._input_locked() and prompt_rows:
            prompt_prefix = f"{self._prompt_prefix()} "
            # The full text up to the logical cursor position in the prompt line.
            cursor_full = prompt_prefix + self._current_input[: self._input_cursor]
            cursor_len = len(cursor_full)
            # Use painter-bound metrics so measurements exactly match what
            # QPainter.drawText renders (avoids DPI / hinting drift).
            painter.setFont(self.text_renderer.font)
            pm = QFontMetricsF(painter.font(), painter.device())
            def _pw(text: str) -> float:
                return pm.horizontalAdvance(text)
            # Walk the wrapped prompt segments to find which visual row and
            # x-offset the cursor lands on.
            consumed = 0
            cursor_y = prompt_rows[0]["y"]
            cursor_x_offset = 0.0
            for prow in prompt_rows:
                seg_len = len(prow["text"])
                if consumed + seg_len >= cursor_len:
                    # Cursor is inside this segment.
                    cursor_x_offset = _pw(cursor_full[consumed:cursor_len])
                    cursor_y = prow["y"]
                    break
                consumed += seg_len
            else:
                # Cursor sits at the very end of the last segment.
                last_prow = prompt_rows[-1]
                cursor_y = last_prow["y"]
                cursor_x_offset = _pw(last_prow["text"])
            cursor_x = term_rect.left() + cursor_x_offset
            cursor_rect = QRectF(
                cursor_x + 1,
                cursor_y + 3,
                max(2.0, _pw(" ") * 0.9),
                self.text_renderer.line_height - 6,
            )
            painter.fillRect(cursor_rect, self.theme.cursor)
            if self.theme.glow:
                glow_pen = QColor(self.theme.cursor)
                glow_pen.setAlpha(90)
                painter.fillRect(cursor_rect.adjusted(-2, -2, 2, 2), glow_pen)

        painter.restore()

        self._paint_status_strip(painter)

        if self._drop_highlight:
            painter.save()
            overlay_pen = QPen(self.theme.accent, 2.0)
            overlay_pen.setCosmetic(True)
            painter.setPen(overlay_pen)
            overlay_fill = QColor(self.theme.accent)
            overlay_fill.setAlpha(24)
            painter.setBrush(overlay_fill)
            painter.drawRoundedRect(term_rect.adjusted(-8, -8, 8, 8), 14, 14)
            painter.restore()

    def _paint_status_strip(self, painter: QPainter) -> None:
        shell_rect = self._shell_rect()
        status_rect = QRectF(shell_rect.left() + 16, shell_rect.bottom() - 28, shell_rect.width() - 32, 18)
        painter.save()
        painter.setPen(self.theme.foreground.darker(135))
        painter.setFont(self.text_renderer.font)
        painter.drawText(
            status_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self._status_text(),
        )
        painter.restore()

    def _paint_text_line(self, painter: QPainter, term_rect: QRectF, y: float, text: str, style: str, row_index: int) -> None:
        color = self.theme.foreground
        if style == "accent":
            color = self.theme.accent
        elif style == "error":
            color = QColor("#ff6b6b")
        elif style == "dim":
            color = self.theme.foreground.darker(130)
        elif style in {"prompt", "prompt_active"}:
            color = self.theme.cursor
        selection = self._selection_for_row(row_index, text)
        if selection is not None:
            left, right = selection
            start_x = term_rect.left() + self.text_renderer.text_width(text[:left])
            end_x = term_rect.left() + self.text_renderer.text_width(text[:right])
            highlight = QColor(self.theme.selection)
            highlight.setAlpha(180)
            painter.fillRect(QRectF(start_x, y + 1, max(1.0, end_x - start_x), self.text_renderer.line_height - 2), highlight)
        self.text_renderer.draw_text(
            painter,
            QRectF(term_rect.left(), y, term_rect.width(), self.text_renderer.line_height),
            text,
            color,
            glow=self.theme.glow,
            glow_color=self.theme.accent,
        )

    def _paint_progress_line(self, painter: QPainter, term_rect: QRectF, y: float, line: TerminalLine, row_index: int, progress_text: str) -> None:
        bar_width = min(term_rect.width() * 0.48, 320.0)
        bar_height = 18.0
        bar_rect = QRectF(term_rect.left(), y + 4, bar_width, bar_height)
        fill_width = max(0.0, min(bar_rect.width(), bar_rect.width() * line.progress))

        painter.save()
        painter.setPen(QPen(QColor(self.theme.foreground.darker(180)), 1.0))
        painter.setBrush(QColor(0, 0, 0, 80))
        painter.drawRoundedRect(bar_rect, 7, 7)

        fill_rect = QRectF(bar_rect.left(), bar_rect.top(), fill_width, bar_rect.height())
        grad = QLinearGradient(fill_rect.left(), fill_rect.top(), fill_rect.right() + 1, fill_rect.top())
        grad.setColorAt(0.0, self.theme.accent.lighter(130))
        grad.setColorAt(1.0, self.theme.accent.darker(110))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(grad)
        painter.drawRoundedRect(fill_rect, 7, 7)

        if self.theme.glow and fill_width > 1:
            glow = QColor(self.theme.accent)
            glow.setAlpha(40)
            painter.setBrush(glow)
            painter.drawRoundedRect(fill_rect.adjusted(-1, -1, 1, 1), 8, 8)

        painter.restore()
        selection = self._selection_for_row(row_index, progress_text)
        if selection is not None:
            left, right = selection
            text_left = bar_rect.right() + 18
            start_x = text_left + self.text_renderer.text_width(progress_text[:left])
            end_x = text_left + self.text_renderer.text_width(progress_text[:right])
            highlight = QColor(self.theme.selection)
            highlight.setAlpha(180)
            painter.fillRect(QRectF(start_x, y + 1, max(1.0, end_x - start_x), self.text_renderer.line_height - 2), highlight)
        self.text_renderer.draw_text(
            painter,
            QRectF(bar_rect.right() + 18, y, term_rect.width() - bar_width - 18, self.text_renderer.line_height + 12),
            progress_text,
            self.theme.foreground,
            glow=self.theme.glow,
            glow_color=self.theme.accent,
        )

    def _paint_matrix_overlay(self, painter: QPainter, term_rect: QRectF) -> None:
        painter.save()
        painter.setClipRect(term_rect)
        glyphs = "01<>[]{}"
        col_width = max(12.0, self.text_renderer.text_width("0"))
        for index, head_y in enumerate(self._matrix_columns):
            x = term_rect.left() + index * col_width
            for trail in range(5):
                y = term_rect.top() + head_y - trail * 18
                if y < term_rect.top() or y > term_rect.bottom():
                    continue
                color = QColor(self.theme.accent)
                color.setAlpha(max(16, 90 - trail * 18))
                self.text_renderer.draw_text(
                    painter,
                    QRectF(x, y, col_width + 6, self.text_renderer.line_height),
                    random.choice(glyphs),
                    color,
                    glow=False,
                )
        painter.restore()

    def _paint_crt_overlay(self, painter: QPainter) -> None:
        shell_rect = self._shell_rect()
        painter.save()
        painter.setClipRect(shell_rect)
        scan_color = QColor(0, 0, 0, 28)
        for y in range(int(shell_rect.top()), int(shell_rect.bottom()), 4):
            painter.fillRect(QRectF(shell_rect.left(), y, shell_rect.width(), 1), scan_color)
        flicker = QColor(255, 255, 255, int(self._crt_flicker * 255))
        painter.fillRect(shell_rect, flicker)
        edge = QLinearGradient(shell_rect.left(), shell_rect.top(), shell_rect.left(), shell_rect.bottom())
        edge.setColorAt(0.0, QColor(255, 0, 70, 10))
        edge.setColorAt(0.5, QColor(0, 0, 0, 0))
        edge.setColorAt(1.0, QColor(0, 180, 255, 12))
        painter.fillRect(shell_rect, edge)
        painter.restore()

    def mousePressEvent(self, event) -> None:
        action = self._title_bar_action_at(event.position())
        if event.button() == Qt.MouseButton.LeftButton and action is not None:
            self._handle_title_bar_action(action)
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton and self._github_link_rect().contains(event.position()):
            QDesktopServices.openUrl(QUrl(self._github_url))
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton and self._title_rect().contains(event.position()):
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton and self._terminal_rect().contains(event.position()):
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            hit = self._hit_test_text_position(event.position())
            if hit is not None:
                self._selection_anchor = hit
                self._selection_cursor = hit
                self._is_selecting = True
                self.update()
                event.accept()
                return
        if event.button() == Qt.MouseButton.RightButton:
            self._show_context_menu(event.globalPosition().toPoint())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        if self._is_selecting and event.buttons() & Qt.MouseButton.LeftButton:
            hit = self._hit_test_text_position(event.position())
            if hit is not None:
                self._selection_cursor = hit
                self.update()
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_offset = None
        if event.button() == Qt.MouseButton.LeftButton and self._is_selecting:
            hit = self._hit_test_text_position(event.position())
            if hit is not None:
                self._selection_cursor = hit
            self._is_selecting = False
            self.update()
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton and self._terminal_rect().contains(event.position()):
            if self._selection_anchor == self._selection_cursor:
                self._clear_selection()
                self.update()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._terminal_rect().contains(event.position()):
            hit = self._hit_test_text_position(event.position())
            if hit is not None:
                row_index, col = hit
                rows = self._build_render_rows()
                row_text = rows[row_index]["text"]
                left = col
                right = col
                while left > 0 and not row_text[left - 1].isspace():
                    left -= 1
                while right < len(row_text) and not row_text[right].isspace():
                    right += 1
                self._selection_anchor = (row_index, left)
                self._selection_cursor = (row_index, right)
                self._is_selecting = False
                self.update()
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def resizeEvent(self, event) -> None:
        self._place_settings_panel()
        shell = self._shell_rect()
        self._scrollbar.setGeometry(
            int(shell.right() - 18),
            int(self._title_bar_height + 20),
            12,
            int(self.height() - self._title_bar_height - self._padding - 30),
        )
        rows = max(20, int(self._terminal_rect().height() / max(1.0, self.text_renderer.line_height)))
        cols = max(40, int(self._terminal_rect().width() / max(1.0, self.text_renderer.cell_width)))
        self.command_runner.resize_session(rows, cols)
        self._sync_scrollbar()
        super().resizeEvent(event)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._drop_highlight = True
            self.update()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dragLeaveEvent(self, event) -> None:
        self._drop_highlight = False
        self.update()
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:
        self._drop_highlight = False
        urls = event.mimeData().urls()
        local_paths = [url.toLocalFile() for url in urls if url.isLocalFile()]
        if not local_paths:
            self.update()
            super().dropEvent(event)
            return
        quoted_paths = " ".join(self._quote_path(path) for path in local_paths if path)
        if quoted_paths:
            if len(local_paths) == 1 and Path(local_paths[0]).is_dir() and not self._current_input.strip():
                self._current_input = f'cd "{local_paths[0]}"'
                self._input_cursor = len(self._current_input)
            else:
                if self._current_input and not self._current_input.endswith(" "):
                    self._current_input += " "
                self._current_input += quoted_paths
                self._input_cursor = len(self._current_input)
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self._mark_activity()
            event.acceptProposedAction()
            self.update()
            return
        self.update()
        super().dropEvent(event)

    def _quote_path(self, path: str) -> str:
        if any(char.isspace() for char in path) or any(char in path for char in "&()[]{}^=;!'+,`~"):
            return f"\"{path}\""
        return path

    def _show_context_menu(self, global_pos: QPoint) -> None:
        menu = QMenu(self)
        copy_action = menu.addAction("Copy")
        paste_action = menu.addAction("Paste")
        clear_action = menu.addAction("Clear")
        copy_action.setEnabled(self._has_selection())
        paste_action.setEnabled(bool(QApplication.clipboard().text()))
        chosen = menu.exec(global_pos)
        if chosen == copy_action:
            self._copy_selection()
        elif chosen == paste_action:
            self._paste_from_clipboard()
        elif chosen == clear_action:
            self._clear_terminal()

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y() / 120.0
        self._auto_scroll_target = min(
            max(0.0, self._auto_scroll_target - delta * self.text_renderer.line_height * 2.2),
            max(0.0, self._content_height() - self._terminal_rect().height()),
        )
        self._mark_activity()
        self._sync_scrollbar()
        self.update()

    def keyPressEvent(self, event) -> None:
        self._mark_activity()
        if event.key() == Qt.Key.Key_Escape:
            if self._settings_open:
                self.toggle_settings()
            else:
                self.close()
            return
        if event.key() == Qt.Key.Key_F2:
            self.cycle_theme()
            return
        if event.key() == Qt.Key.Key_F3:
            self.toggle_settings()
            return
        if event.key() == Qt.Key.Key_F11:
            self.setWindowState(self.windowState() ^ Qt.WindowState.WindowFullScreen)
            return
        if event.key() == Qt.Key.Key_Q and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            QApplication.quit()
            return
        if event.key() == Qt.Key.Key_V and event.modifiers() == (
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
        ):
            self._paste_from_clipboard()
            return
        if event.key() == Qt.Key.Key_V and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._paste_from_clipboard()
            return
        if event.key() == Qt.Key.Key_A and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            rows = self._build_render_rows()
            if rows:
                self._selection_anchor = (0, 0)
                last_row = len(rows) - 1
                self._selection_cursor = (last_row, len(rows[last_row]["text"]))
                self.update()
            return
        if event.key() == Qt.Key.Key_C and event.modifiers() == (
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
        ):
            self._copy_selection()
            return
        if event.key() == Qt.Key.Key_C and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if self._copy_selection():
                return
            self.command_runner.stop()
            self._append_output("^C", "error")
            return
        if event.key() == Qt.Key.Key_Left:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self._move_cursor_word_left()
            else:
                self._input_cursor = max(0, self._input_cursor - 1)
            self.update()
            return
        if event.key() == Qt.Key.Key_Right:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self._move_cursor_word_right()
            else:
                self._input_cursor = min(len(self._current_input), self._input_cursor + 1)
            self.update()
            return
        if event.key() == Qt.Key.Key_Home:
            self._input_cursor = 0
            self.update()
            return
        if event.key() == Qt.Key.Key_End:
            self._input_cursor = len(self._current_input)
            self.update()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._clear_selection()
            self._submit_current_command()
            return
        if event.key() == Qt.Key.Key_Delete:
            self._clear_selection()
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self._delete_word_forward()
            else:
                self._delete_forward()
            self.update()
            return
        if event.key() == Qt.Key.Key_Backspace:
            self._clear_selection()
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self._delete_word_backward()
            else:
                self._delete_backward()
            self.update()
            return
        if event.key() == Qt.Key.Key_Up:
            self._history_move(-1)
            return
        if event.key() == Qt.Key.Key_Down:
            self._history_move(1)
            return
        if event.key() == Qt.Key.Key_L and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._clear_terminal()
            return
        if not self._input_locked():
            text = event.text()
            if text and text >= " ":
                self._clear_selection()
                self._insert_text_at_cursor(text)
                self.update()
                return
        super().keyPressEvent(event)
