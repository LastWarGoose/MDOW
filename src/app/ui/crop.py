from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from app.ui.style import STYLE


class CropCanvas(QWidget):
    changed = Signal()

    def __init__(self, source, parent=None):
        super().__init__(parent)
        self.image_width, self.image_height = source.image.size
        self.preview = QPixmap()
        self.preview.loadFromData(source.preview)
        side = min(self.image_width, self.image_height)
        self.crop = QRectF(
            (self.image_width - side) / 2, (self.image_height - side) / 2, side, side
        )
        self.mode = None
        self.offset = QPointF()
        self.setMinimumSize(360, 280)
        self.setMouseTracking(True)
        self.setAccessibleName(
            "Квадратная область обложки: перетащите рамку или её нижний правый угол"
        )

    def image_rect(self):
        scale = min(
            (self.width() - 32) / self.image_width, (self.height() - 32) / self.image_height
        )
        width, height = self.image_width * scale, self.image_height * scale
        return QRectF((self.width() - width) / 2, (self.height() - height) / 2, width, height)

    def screen_crop(self):
        rect = self.image_rect()
        scale = rect.width() / self.image_width
        return QRectF(
            rect.x() + self.crop.x() * scale,
            rect.y() + self.crop.y() * scale,
            self.crop.width() * scale,
            self.crop.height() * scale,
        )

    def image_point(self, point):
        rect = self.image_rect()
        return (point - rect.topLeft()) / (rect.width() / self.image_width)

    def set_crop(self, x, y, side):
        side = max(1, min(side, self.image_width, self.image_height))
        x = max(0, min(x, self.image_width - side))
        y = max(0, min(y, self.image_height - side))
        self.crop = QRectF(x, y, side, side)
        self.update()
        self.changed.emit()

    def set_percentage(self, percentage):
        side = max(1, min(self.image_width, self.image_height) * percentage / 100)
        center = self.crop.center()
        self.set_crop(center.x() - side / 2, center.y() - side / 2, side)

    def selection(self):
        side = max(1, min(round(self.crop.width()), self.image_width, self.image_height))
        x = max(0, min(round(self.crop.x()), self.image_width - side))
        y = max(0, min(round(self.crop.y()), self.image_height - side))
        return x, y, side

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor("#0b0b0c"))
        rect = self.image_rect()
        painter.drawPixmap(rect, self.preview, QRectF(self.preview.rect()))
        selected = self.screen_crop()
        outside, inside = QPainterPath(), QPainterPath()
        outside.addRect(rect)
        inside.addRect(selected)
        painter.fillPath(outside.subtracted(inside), QColor(0, 0, 0, 170))
        painter.setPen(QPen(QColor("#ff7800"), 2))
        painter.drawRect(selected)
        painter.setPen(QPen(QColor(255, 220, 182, 100), 1))
        for fraction in (1 / 3, 2 / 3):
            x, y = (
                selected.x() + selected.width() * fraction,
                selected.y() + selected.height() * fraction,
            )
            painter.drawLine(QPointF(x, selected.top()), QPointF(x, selected.bottom()))
            painter.drawLine(QPointF(selected.left(), y), QPointF(selected.right(), y))
        painter.fillRect(
            QRectF(selected.bottomRight() - QPointF(6, 6), selected.bottomRight() + QPointF(6, 6)),
            QColor("#ff941f"),
        )

    def near_handle(self, point):
        delta = point - self.screen_crop().bottomRight()
        return abs(delta.x()) < 15 and abs(delta.y()) < 15

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        point = event.position()
        if self.near_handle(point):
            self.mode = "resize"
        elif self.image_rect().contains(point):
            self.mode = "move"
            image_point = self.image_point(point)
            if not self.screen_crop().contains(point):
                self.set_crop(
                    image_point.x() - self.crop.width() / 2,
                    image_point.y() - self.crop.height() / 2,
                    self.crop.width(),
                )
            self.offset = image_point - self.crop.topLeft()

    def mouseMoveEvent(self, event):
        point = event.position()
        image_point = self.image_point(point)
        if self.mode == "move":
            self.set_crop(
                image_point.x() - self.offset.x(),
                image_point.y() - self.offset.y(),
                self.crop.width(),
            )
        elif self.mode == "resize":
            side = max(
                1,
                min(
                    max(image_point.x() - self.crop.x(), image_point.y() - self.crop.y()),
                    self.image_width - self.crop.x(),
                    self.image_height - self.crop.y(),
                ),
            )
            self.set_crop(self.crop.x(), self.crop.y(), side)
        else:
            cursor = (
                Qt.CursorShape.SizeFDiagCursor
                if self.near_handle(point)
                else Qt.CursorShape.SizeAllCursor
            )
            self.setCursor(cursor)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.mode = None


class CropDialog(QDialog):
    def __init__(self, source, parent=None):
        super().__init__(parent)
        self.setWindowTitle("MDOW — кадрирование обложки")
        self.setStyleSheet(STYLE)
        self.resize(700, 680)
        self.setMinimumSize(480, 520)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(14)
        heading = QLabel("Выберите фрагмент обложки")
        heading.setObjectName("heading")
        layout.addWidget(heading)
        hint = QLabel("Двигайте квадрат мышью. Потяните за угол, чтобы изменить размер.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.canvas = CropCanvas(source)
        layout.addWidget(self.canvas, 1)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Размер области"))
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(1, 100)
        self.slider.setValue(100)
        self.slider.setAccessibleName("Размер квадратной области в процентах")
        self.slider.valueChanged.connect(self.canvas.set_percentage)
        controls.addWidget(self.slider, 1)
        self.size_label = QLabel()
        self.size_label.setObjectName("cropSize")
        controls.addWidget(self.size_label)
        layout.addLayout(controls)
        self.canvas.changed.connect(self.update_size)
        self.update_size()
        actions = QHBoxLayout()
        reset = QPushButton("Сбросить")
        reset.clicked.connect(self.reset)
        actions.addWidget(reset)
        actions.addStretch()
        cancel = QPushButton("Отмена")
        cancel.clicked.connect(self.reject)
        self.apply_button = QPushButton("Применить обложку")
        self.apply_button.setObjectName("primary")
        self.apply_button.clicked.connect(self.accept)
        self.apply_button.setDefault(True)
        actions.addWidget(cancel)
        actions.addWidget(self.apply_button)
        layout.addLayout(actions)

    def update_size(self):
        side = self.canvas.selection()[2]
        self.size_label.setText(f"{side} × {side}")
        self.slider.blockSignals(True)
        self.slider.setValue(
            max(1, round(side * 100 / min(self.canvas.image_width, self.canvas.image_height)))
        )
        self.slider.blockSignals(False)

    def reset(self):
        side = min(self.canvas.image_width, self.canvas.image_height)
        self.canvas.set_crop(
            (self.canvas.image_width - side) / 2, (self.canvas.image_height - side) / 2, side
        )

    def selection(self):
        return self.canvas.selection()
