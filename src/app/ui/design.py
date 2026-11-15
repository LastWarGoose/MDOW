from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QFrame, QWidget


class IndustrialBackground(QWidget):
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#111112"))
        glow = QRadialGradient(QPointF(self.width() * 0.85, -60), self.width() * 0.8)
        glow.setColorAt(0, QColor(110, 51, 14, 70))
        glow.setColorAt(1, QColor(17, 17, 18, 0))
        painter.fillRect(self.rect(), glow)
        painter.setPen(QPen(QColor(224, 116, 37, 12), 1))
        for x in range(16, self.width(), 24):
            for y in range(16, self.height(), 24):
                painter.drawPoint(x, y)


class IndustrialPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setPen(QPen(QColor("#9d572a"), 2))
        painter.drawLine(1, 13, 1, 1)
        painter.drawLine(1, 1, 22, 1)
        painter.setPen(QPen(QColor("#6f4429"), 1))
        painter.drawLine(self.width() - 22, self.height() - 2, self.width() - 2, self.height() - 2)
        painter.drawLine(self.width() - 2, self.height() - 2, self.width() - 2, self.height() - 14)
