from io import BytesIO

import pytest
from PIL import Image
from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QColor, QDragEnterEvent, QDropEvent, QImage
from PySide6.QtWidgets import QApplication, QDialog

from app.adapters.covers import crop_cover, load_cover_source
from app.models.task import AppError, Cancellation, Cancelled, Tags
from app.ui.cover_import import CoverDropArea, clipboard_cover_source, mime_source
from app.ui.crop import CropDialog
from app.ui.window import MainWindow


@pytest.fixture
def picture_bytes():
    picture = Image.new("RGB", (2400, 1200), "#e47719")
    picture.paste("#154dbb", (1200, 0, 2400, 1200))
    stream = BytesIO()
    picture.save(stream, "PNG")
    return stream.getvalue()


def test_square_crop_uses_original_resolution(picture_bytes):
    source = load_cover_source(picture_bytes, Cancellation())
    with Image.open(BytesIO(source.preview)) as preview:
        assert preview.size == (1000, 500)
    for x, expected in [(0, (228, 119, 25)), (1200, (21, 77, 187))]:
        result = crop_cover(source, (x, 0, 1200), Cancellation())
        with Image.open(BytesIO(result)) as output:
            assert output.size == (1200, 1200)
            assert (
                max(abs(a - b) for a, b in zip(output.getpixel((600, 600)), expected, strict=True))
                < 4
            )


def test_exif_orientation_applied_before_selecting():
    picture = Image.new("RGB", (80, 40), "orange")
    exif = Image.Exif()
    exif[274] = 6
    stream = BytesIO()
    picture.save(stream, "JPEG", exif=exif)
    source = load_cover_source(stream.getvalue(), Cancellation())
    assert source.image.size == (40, 80)
    result = crop_cover(source, (0, 40, 40), Cancellation())
    with Image.open(BytesIO(result)) as output:
        assert output.size == (40, 40)
        assert output.getexif().get(274) is None


@pytest.mark.parametrize("selection", [(-1, 0, 10), (0, 0, 0), (2000, 0, 1200), (0, 600, 800)])
def test_invalid_selection(picture_bytes, selection):
    source = load_cover_source(picture_bytes, Cancellation())
    with pytest.raises(AppError):
        crop_cover(source, selection, Cancellation())


def test_cancelled_crop(picture_bytes):
    source = load_cover_source(picture_bytes, Cancellation())
    cancel = Cancellation()
    cancel.cancel()
    with pytest.raises(Cancelled):
        crop_cover(source, (0, 0, 100), cancel)


def test_clipboard_pixels_and_local_file(qtbot, tmp_path):
    image = QImage(73, 51, QImage.Format.Format_RGB888)
    image.fill(QColor("#ff8000"))
    mime = QMimeData()
    mime.setImageData(image)
    snapshot = mime_source(mime)
    source = clipboard_cover_source(snapshot, Cancellation())
    assert source.image.size == (73, 51)
    assert source.image.getpixel((50, 20)) == (255, 128, 0, 255)
    file = tmp_path / "обложка.png"
    image.save(str(file))
    file_mime = QMimeData()
    file_mime.setUrls([QUrl.fromLocalFile(str(file))])
    assert mime_source(file_mime) == file


def test_remote_url_and_empty_clipboard_are_rejected():
    mime = QMimeData()
    mime.setUrls([QUrl("https://example.com/image.jpg")])
    for value in (mime, QMimeData(), None):
        with pytest.raises(AppError):
            mime_source(value)


def test_drop_delivers_image(qtbot, picture_bytes):
    area = CoverDropArea()
    qtbot.addWidget(area)
    area.show()
    mime = QMimeData()
    mime.setData("image/png", picture_bytes)
    received = []
    area.dropped.connect(lambda data: received.append(mime_source(data)))
    enter = QDragEnterEvent(
        QPointF(40, 40),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(area, enter)
    assert enter.isAccepted()
    drop = QDropEvent(
        QPointF(40, 40),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(area, drop)
    assert drop.isAccepted()
    assert received == [picture_bytes]


def test_crop_drag_resize_stays_square_and_in_bounds(qtbot, picture_bytes):
    dialog = CropDialog(load_cover_source(picture_bytes, Cancellation()))
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.slider.setValue(50)
    assert dialog.selection()[2] == 600
    canvas = dialog.canvas
    start = canvas.screen_crop().center().toPoint()
    qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=start)
    qtbot.mouseMove(canvas, pos=start + QPoint(90, 10))
    qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=start + QPoint(90, 10))
    x, y, side = dialog.selection()
    assert x > 900
    assert 0 <= y <= 1200 - side
    handle = canvas.screen_crop().bottomRight().toPoint()
    qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=handle)
    qtbot.mouseMove(canvas, pos=handle - QPoint(35, 35))
    qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=handle - QPoint(35, 35))
    assert dialog.selection()[2] < 600
    assert canvas.crop.width() == canvas.crop.height()
    dialog.reset()
    assert dialog.selection() == (600, 0, 1200)


def test_cancel_crop_keeps_old_cover(qtbot, picture_bytes, monkeypatch):
    window = MainWindow(check_tools=False)
    qtbot.addWidget(window)
    source = load_cover_source(picture_bytes, Cancellation())
    old = crop_cover(source, (0, 0, 400), Cancellation())
    window.on_metadata(Tags(cover=old))
    window.dirty = False
    monkeypatch.setattr(CropDialog, "exec", lambda _: QDialog.DialogCode.Rejected)
    window.select_cover_crop(source)
    assert window.cover_data == old
    assert not window.dirty


def test_import_crop_apply_async(qtbot, picture_bytes, monkeypatch):
    window = MainWindow(check_tools=False)
    qtbot.addWidget(window)
    window.on_metadata(Tags(title="Трек"))

    def select(dialog):
        dialog.canvas.set_crop(1200, 0, 1200)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(CropDialog, "exec", select)
    window.import_cover_source(picture_bytes)
    qtbot.waitUntil(lambda: window.worker is None, timeout=10000)
    assert window.cover_data
    with Image.open(BytesIO(window.cover_data)) as cover:
        assert cover.size == (1200, 1200)
        assert cover.getpixel((500, 500))[2] > 180
    window.dirty = False


def test_paste_keys_read_clipboard_image(qtbot, picture_bytes, monkeypatch):
    window = MainWindow(check_tools=False)
    qtbot.addWidget(window)
    window.on_metadata(Tags())
    mime = QMimeData()
    mime.setData("image/png", picture_bytes)

    class Clipboard:
        def mimeData(self):
            return mime

    monkeypatch.setattr(QApplication, "clipboard", lambda: Clipboard())
    imported = []
    monkeypatch.setattr(window, "import_cover_source", imported.append)
    qtbot.keyClick(window.cover, Qt.Key.Key_V, modifier=Qt.KeyboardModifier.ControlModifier)
    assert imported == [picture_bytes]
    window.dirty = False
