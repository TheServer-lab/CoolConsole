from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetricsF, QPainter


class TextRenderer:
    def __init__(self, font_family: str, font_size: int) -> None:
        self.font = QFont(font_family, font_size)
        self.font.setStyleHint(QFont.StyleHint.Monospace)
        self.metrics = QFontMetricsF(self.font)

    def set_font(self, font_family: str, font_size: int) -> None:
        self.font = QFont(font_family, font_size)
        self.font.setStyleHint(QFont.StyleHint.Monospace)
        self.metrics = QFontMetricsF(self.font)

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

    def baseline(self, top: float) -> float:
        return top + self.metrics.ascent()
