import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from app.models.task import Tags
from app.ui.window import MainWindow


def test_initial_controls(qtbot, monkeypatch):
    window = MainWindow(check_tools=False)
    qtbot.addWidget(window)
    window.show()
    assert window.download_button.isEnabled()
    assert not window.editor.isEnabled()
    assert not window.save_button.isEnabled()
    window.url.setText("https://youtu.be/abcdefgh_-1")
    prepared = []
    monkeypatch.setattr(window, "prepare", lambda *args: prepared.append(args))
    window.start_download()
    assert prepared == [("https://www.youtube.com/watch?v=abcdefgh_-1", True)]
    assert not hasattr(window, "consent")
    assert window.terms_button.text() == "Условия YouTube ↗"
    assert window.worker is None


@pytest.mark.parametrize("maximized", [False, True])
@pytest.mark.parametrize("key", [Qt.Key.Key_Return, Qt.Key.Key_Enter])
def test_fullscreen_shortcut_restores_window(qtbot, maximized, key):
    window = MainWindow(check_tools=False)
    qtbot.addWidget(window)
    window.on_metadata(Tags())
    window.dirty = False
    with qtbot.waitExposed(window):
        window.showMaximized() if maximized else window.show()
    window.activateWindow()
    qtbot.waitUntil(window.isActiveWindow)
    window.lyrics.setFocus()
    qtbot.wait(50)
    geometry = window.geometry()
    qtbot.keyClick(window.lyrics, key, modifier=Qt.KeyboardModifier.AltModifier)
    qtbot.waitUntil(window.isFullScreen)
    assert window.windowHandle().safeAreaMargins().top() == 0
    qtbot.wait(50)
    qtbot.keyClick(window.lyrics, key, modifier=Qt.KeyboardModifier.AltModifier)
    qtbot.waitUntil(lambda: not window.isFullScreen())
    qtbot.waitUntil(lambda: window.isMaximized() == maximized)
    qtbot.waitUntil(lambda: window.geometry() == geometry)
    assert window.worker is None


def test_error_remains_visible_without_footer_message(qtbot):
    window = MainWindow(check_tools=False)
    qtbot.addWidget(window)
    window.show()
    window.on_error("Не удалось открыть <файл>.")
    dialog = window.findChild(QMessageBox)
    assert dialog.isVisible()
    assert dialog.text() == "Не удалось открыть <файл>."
    assert dialog.textFormat() == Qt.TextFormat.PlainText
    dialog.accept()


def test_metadata_changes_survive_completion(qtbot, tmp_path):
    window = MainWindow(check_tools=False)
    qtbot.addWidget(window)
    window.on_metadata(Tags(title="Из YouTube"))
    assert window.editor.isEnabled()
    window.title_input.setText("Моё название")
    window.lyrics.setPlainText("Мой текст\nВторая строка")
    window.audio_ready({"duration": 65, "path": tmp_path / "working.mp3"})
    window.update_controls()
    assert window.title_input.text() == "Моё название"
    assert window.lyrics.toPlainText() == "Мой текст\nВторая строка"
    assert window.save_button.isEnabled()
    window.lyrics.setPlainText("x" * 100001)
    assert not window.save_button.isEnabled()
    window.dirty = False


def test_import_responsive(qtbot, tone):
    window = MainWindow(check_tools=False)
    qtbot.addWidget(window)
    window.show()
    window.prepare(tone, False)
    assert window.cancel_button.isEnabled()
    assert not window.import_button.isEnabled()
    qtbot.waitUntil(lambda: window.worker is None, timeout=20000)
    assert window.ready, window.status_message
    assert window.save_button.isEnabled()
    window.dirty = False
    window.close()


def test_save_from_window(qtbot, tone, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    from app.adapters.tags import TagAdapter

    window = MainWindow(check_tools=False)
    qtbot.addWidget(window)
    window.prepare(tone, False)
    qtbot.waitUntil(lambda: window.worker is None, timeout=20000)
    window.title_input.setText("Песня из окна")
    window.artist_input.setText("Исполнитель")
    window.lyrics.setPlainText("Один\nДва")
    destination = tmp_path / "ui-saved.mp3"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", lambda *a, **kw: (str(destination), "MP3 (*.mp3)")
    )
    window.save_file()
    qtbot.waitUntil(lambda: window.worker is None, timeout=20000)
    assert destination.exists(), window.status_message
    assert TagAdapter().read(destination).title == "Песня из окна"
    assert TagAdapter().read(destination).lyrics == "Один\nДва"
    assert not window.dirty
    window.close()
