from __future__ import annotations

from PyQt6.QtCore import QObject, QTimer


class CursorController(QObject):
    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.visible = True
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._toggle)
        self._timer.start(530)

    def _toggle(self) -> None:
        self.visible = not self.visible
