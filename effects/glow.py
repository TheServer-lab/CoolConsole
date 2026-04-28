from __future__ import annotations

from PyQt6.QtGui import QColor, QPainter, QRadialGradient
from PyQt6.QtCore import QPointF


def paint_panel_glow(
    painter: QPainter,
    center: QPointF,
    radius: float,
    color: QColor,
    alpha: int = 90,
) -> None:
    glow = QRadialGradient(center, radius)
    core = QColor(color)
    core.setAlpha(alpha)
    edge = QColor(color)
    edge.setAlpha(0)
    glow.setColorAt(0.0, core)
    glow.setColorAt(1.0, edge)
    painter.save()
    painter.setBrush(glow)
    painter.setPen(QColor(0, 0, 0, 0))
    painter.drawEllipse(center, radius, radius)
    painter.restore()
