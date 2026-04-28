from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetricsF, QPainter


class TextRenderer:
    def __init__(self, font_family: str, font_size: int) -> None:
        self.font = QFont(font_family, font_size)
        self.font.setStyleHint(QFont.StyleHint.Monospace)
        self.metrics = QFontMetricsF(self.font)
        self._cell_width = max(self.metrics.horizontalAdvance("M"), self.metrics.horizontalAdvance(" "))

    def set_font(self, font_family: str, font_size: int) -> None:
        self.font = QFont(font_family, font_size)
        self.font.setStyleHint(QFont.StyleHint.Monospace)
        self.metrics = QFontMetricsF(self.font)
        self._cell_width = max(self.metrics.horizontalAdvance("M"), self.metrics.horizontalAdvance(" "))

    @property
    def line_height(self) -> float:
        return self.metrics.lineSpacing() + 6.0

    def draw_text(
        self,
        painter: QPainter,
        rect: QRectF,
        text: str,
        color: QColor,
        glow: bool = False,
        glow_color: QColor | None = None,
    ) -> None:
        painter.save()
        painter.setFont(self.font)
        painter.setPen(color)

        if glow:
            aura = glow_color or color
            for alpha, offset in ((55, 0.0), (25, 0.8), (10, 1.6)):
                glow_pen = QColor(aura)
                glow_pen.setAlpha(alpha)
                painter.setPen(glow_pen)
                painter.drawText(rect.translated(offset, 0.0), Qt.AlignmentFlag.AlignLeft, text)
            painter.setPen(color)

        painter.drawText(rect, Qt.AlignmentFlag.AlignLeft, text)
        painter.restore()

    def text_width(self, text: str) -> float:
        return self.metrics.horizontalAdvance(text)

    @property
    def cell_width(self) -> float:
        return self._cell_width

    def monospace_text_width(self, text: str) -> float:
        return len(text) * self._cell_width

    def baseline(self, top: float) -> float:
        return top + self.metrics.ascent()

    def wrap_line(self, text: str, max_width: float) -> list[str]:
        """Split *text* into segments that each fit within *max_width* pixels.

        Always returns at least one element (possibly an empty string).
        """
        if not text:
            return [text]
        if max_width <= 0 or self.text_width(text) <= max_width:
            return [text]
        segments: list[str] = []
        remaining = text
        while remaining:
            # Binary-search for the longest prefix that fits.
            lo, hi = 0, len(remaining)
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if self.text_width(remaining[:mid]) <= max_width:
                    lo = mid
                else:
                    hi = mid - 1
            cut = max(1, lo)  # always advance at least one char to avoid infinite loop
            segments.append(remaining[:cut])
            remaining = remaining[cut:]
        return segments
