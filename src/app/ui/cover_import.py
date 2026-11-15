from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QImage, QKeySequence, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from app.adapters.covers import MAX_COVER_SOURCE, MAX_PIXELS, CoverSource, encode_cover
from app.models.task import AppError


def mime_source(mime):
    """Snapshot a local file or image while MIME ownership still belongs to Qt."""
    if mime is None:
        raise AppError("В буфере обмена нет изображения.")
    if mime.hasUrls():
        urls = mime.urls()
        if len(urls) == 1 and urls[0].isLocalFile():
            return Path(urls[0].toLocalFile())
    for kind in ("image/png", "image/jpeg", "image/webp", "image/bmp"):
        if mime.hasFormat(kind):
            data = mime.data(kind)
            if data.size() > MAX_COVER_SOURCE:
                raise AppError("Исходная обложка должна быть не больше 10 МБ.")
            return bytes(data)
    if mime.hasImage():
        image = mime.imageData()
        if isinstance(image, QPixmap):
            image = image.toImage()
        if isinstance(image, QImage) and not image.isNull():
            if image.width() * image.height() > MAX_PIXELS:
                raise AppError("Обложка должна содержать не больше 25 мегапикселей.")
            return QImage(image)
    raise AppError(
        "Нужно изображение или один локальный файл. В браузере выберите «Копировать изображение»."
    )


def clipboard_cover_source(image: QImage, cancel):
    from PIL import Image

    cancel.check()
    if image.isNull() or image.width() * image.height() > MAX_PIXELS:
        raise AppError("Буфер содержит пустое или слишком большое изображение.")
    pixels = image.convertToFormat(QImage.Format.Format_RGBA8888)
    picture = Image.frombytes("RGBA", (pixels.width(), pixels.height()), bytes(pixels.constBits()))
    preview = encode_cover(picture, maximum=1000)
    cancel.check()
    return CoverSource(picture, preview)


class CoverDropArea(QWidget):
    dropped = Signal(object)
    chooseRequested = Signal()
    pasteRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pixmap = QPixmap()
        self.drag_over = False
        self.setFixedSize(220, 220)
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName("Обложка: перетащите изображение или вставьте Ctrl+V")
        self.setToolTip(
            "Перетащите файл или изображение. Ctrl+V — вставить обложку. Нажмите для выбора файла."
        )

    def set_image(self, data):
        self.pixmap = QPixmap()
        if data:
            self.pixmap.loadFromData(data)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#101010"))
        if not self.pixmap.isNull():
            image = self.pixmap.scaled(
                self.size() - QSize(12, 12),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            painter.drawPixmap(
                (self.width() - image.width()) // 2, (self.height() - image.height()) // 2, image
            )
        accent = QColor("#ff7800" if self.drag_over or self.hasFocus() else "#82502d")
        painter.setPen(QPen(accent, 2))
        w, h = self.width() - 2, self.height() - 2
        for x, y, dx, dy in [(1, 1, 1, 1), (w, 1, -1, 1), (1, h, 1, -1), (w, h, -1, -1)]:
            painter.drawLine(x, y, x + dx * 20, y)
            painter.drawLine(x, y, x, y + dy * 20)
        if self.drag_over:
            painter.fillRect(self.rect(), QColor(255, 129, 35, 30))

    def dragEnterEvent(self, event):
        if self.isEnabled() and (
            event.mimeData().hasImage()
            or event.mimeData().hasUrls()
            or any(f.startswith("image/") for f in event.mimeData().formats())
        ):
            self.drag_over = True
            self.update()
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self.drag_over = False
        self.update()
        event.accept()

    def dropEvent(self, event):
        self.drag_over = False
        self.update()
        if self.isEnabled():
            self.dropped.emit(event.mimeData())
            event.acceptProposedAction()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
            event.position().toPoint()
        ):
            self.chooseRequested.emit()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Paste):
            self.pasteRequested.emit()
            event.accept()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Space):
            self.chooseRequested.emit()
        else:
            super().keyPressEvent(event)
