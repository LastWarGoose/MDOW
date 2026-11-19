import json
import shutil
from io import BytesIO
from threading import Event

import pytest
from PIL import Image
from PySide6.QtCore import QTimer
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QComboBox, QFileDialog, QInputDialog
from yt_dlp.extractor.youtube import YoutubeSearchIE
from yt_dlp.utils import ExtractorError

from app.adapters import lookup_worker as remote
from app.adapters.tags import TagAdapter
from app.models.task import AppError, Cancellation, Tags
from app.services.audio import AudioService
from app.services.lookup import LookupService, is_search, run_lookup
from app.ui.window import MainWindow

URL = "https://www.youtube.com/watch?v=abcdefgh_-1"


@pytest.mark.parametrize(
    "value",
    [
        "http://localhost/test",
        "file:///x.wav",
        "D:\\songs\\a.mp3",
        "//example.org",
        "youtu.be/abcdefgh_-1",
        "track.mp3",
        URL,
    ],
)
def test_addresses_are_not_sent_to_search(value):
    assert not is_search(value)
    assert is_search("AC/DC — Thunderstruck")


def test_youtube_results(monkeypatch):
    def results(self, query):
        assert query == "Музыка & песня"
        item = dict(id="abcdefgh_-1", ie_key="Youtube", title="Rock & Roll", channel="Лейбл")
        yield {**item, "url": "https://example.com/untrusted", "duration": 225}
        yield {**item, "live_status": "is_live"}
        yield {**item, "id": "invalid-id"}
        yield {**item, "ie_key": "YoutubeTab"}
        yield {**item, "title": ""}
        pytest.fail("Поиск должен читать только первые пять результатов")

    monkeypatch.setattr(YoutubeSearchIE, "_search_results", results)
    assert remote.search("Музыка & песня") == [
        dict(url=URL, title="Rock & Roll", channel="Лейбл", duration=225)
    ]


def test_search_reports_unavailability(monkeypatch):
    def unavailable(self, query):
        raise ExtractorError("private diagnostics", expected=True)

    monkeypatch.setattr(YoutubeSearchIE, "_search_results", unavailable)
    with pytest.raises(AppError, match="вставьте ссылку") as error:
        remote.search("Трек")
    assert "private diagnostics" not in str(error.value)


def test_lyrics_require_matching_recording(monkeypatch):
    record = dict(
        trackName="Песня",
        artistName="Артист",
        albumName="Альбом",
        duration=180,
        plainLyrics="Строка раз\nСтрока два",
        instrumental=False,
    )
    rows = [record]
    monkeypatch.setattr(remote, "fetch", lambda *_: json.dumps(rows))
    assert (
        remote.lookup_track("Артист — Песня (Official Video)", "", 182)["lyrics"]
        == record["plainLyrics"]
    )
    assert not remote.lookup_track("Песня", "", 200)
    assert "lyrics" not in remote.lookup_track("Песня", "Артист", 200)
    assert not remote.lookup_track("Песня (Live)", "Артист", 180)
    rows.append({**record, "artistName": "Другой"})
    assert not remote.lookup_track("Песня", "", 180)
    rows[0]["instrumental"] = True
    assert not remote.lookup_track("Песня", "Артист", 180)["lyrics"]


def test_unavailable_lyrics_still_returns_original_thumbnail(tmp_path, monkeypatch):
    calls = []

    def fetch(host, path, **kwargs):
        calls.append(host)
        if host == "lrclib.net" or path.endswith("maxresdefault.jpg"):
            raise remote.ServiceError(404)
        return b"image bytes"

    monkeypatch.setattr(remote, "fetch", fetch)
    info = remote.enrich(dict(url=URL, title="Трек", artist="", duration=181), tmp_path)
    assert info["issues"] and not info["tags"]
    assert (tmp_path / "thumbnail").read_bytes() == b"image bytes"
    assert calls == ["lrclib.net", "i.ytimg.com", "i.ytimg.com"]


def test_search_cancel_keeps_existing_track(qtbot, monkeypatch):
    lookup = LookupService()
    win = MainWindow(check_tools=False, lookup=lookup)
    qtbot.addWidget(win)
    win.on_metadata(Tags(title="Моя правка"))
    monkeypatch.setattr(
        lookup, "search", lambda *args: [dict(url=URL, title="Трек", channel="Канал")]
    )
    monkeypatch.setattr(QInputDialog, "getItem", lambda *args: ("", False))
    win.url.setText("Песня")
    win.start_download()
    qtbot.waitUntil(lambda: win.worker is None)
    assert win.title_input.text() == "Моя правка" and win.dirty
    win.dirty = False


def test_result_picker_durations_and_text_colors(qtbot, monkeypatch):
    win = MainWindow(check_tools=False)
    qtbot.addWidget(win)
    second_url = "https://www.youtube.com/watch?v=abcdefgh_-2"
    choices = [
        dict(url=URL, title="Трек", channel="Группа", duration=225),
        dict(url=second_url, title="Концерт", channel="", duration=3724),
        dict(url=URL, title="Редкая запись", channel=""),
    ]
    selected, rows, colors = [], [], []
    monkeypatch.setattr(win, "prepare", lambda url, is_url: selected.append(url))

    def inspect_and_select():
        dialog = QApplication.activeModalWidget()
        try:
            combo = dialog.findChild(QComboBox)
            rows.extend(combo.itemText(i) for i in range(combo.count()))
            combo.showPopup()
            view = combo.view()
            roles = QPalette.ColorRole
            colors.extend(
                [
                    combo.palette().color(roles.ButtonText).name(),
                    view.palette().color(roles.Text).name(),
                    view.palette().color(roles.HighlightedText).name(),
                    combo.palette().color(roles.Button).name(),
                    view.palette().color(roles.Base).name(),
                    view.palette().color(roles.Highlight).name(),
                ]
            )
            combo.hidePopup()
            combo.setCurrentIndex(1)
        finally:
            dialog.accept()

    QTimer.singleShot(0, inspect_and_select)
    win.choose_result(choices)
    assert rows == [
        "1.  [3:45]  Трек · Группа",
        "2.  [1:02:04]  Концерт",
        "3.  [время не указано]  Редкая запись",
    ]
    assert colors == ["#ffffff"] * 3 + ["#303030", "#303030", "#505050"]
    assert selected == [second_url]


def test_search_to_tagged_mp3(qtbot, monkeypatch, tone, tmp_path):
    waiting, allow_lookup = Event(), Event()
    words = "Тестовая строка\nВторая строка"
    image = BytesIO()
    Image.new("RGB", (200, 100), "orange").save(image, "JPEG")

    def lookup_request(mode, folder, request, cancel):
        if mode == "search":
            return [dict(url=URL, title="Трек", channel="Канал")]
        waiting.set()
        assert allow_lookup.wait(5)
        (folder / "thumbnail").write_bytes(image.getvalue())
        return dict(
            tags=dict(title="Название", artist="Исполнитель", album="Альбом", lyrics=words),
            issues=[],
        )

    monkeypatch.setattr("app.services.lookup.run_lookup", lookup_request)

    class Downloader:
        def download(self, url, folder, cancel, metadata, progress, downloading):
            assert url == URL
            metadata(Tags(title="Видео"))
            downloading()
            return shutil.copy(tone, folder / "tone.wav")

    win = MainWindow(service=AudioService(downloader=Downloader()), check_tools=False)
    qtbot.addWidget(win)
    monkeypatch.setattr(QInputDialog, "getText", lambda *a: pytest.fail("Неожиданный запрос ключа"))
    monkeypatch.setattr(
        QInputDialog, "getItem", lambda parent, title, label, items, *_: (items[0], True)
    )
    win.url.setText("Найди песню")
    win.start_download()
    try:
        qtbot.waitUntil(waiting.is_set, timeout=20000)
        win.title_input.setText("Моё название")
    finally:
        allow_lookup.set()
    qtbot.waitUntil(lambda: win.worker is None, timeout=10000)
    assert win.cover_source.image.size == (200, 100)
    assert Image.open(BytesIO(win.cover_data)).size == (100, 100)
    dest = tmp_path / "готово.mp3"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **kw: (str(dest), ""))
    win.save_file()
    qtbot.waitUntil(lambda: win.worker is None)
    assert TagAdapter().read(dest) == Tags(
        "Моё название", "Исполнитель", "Альбом", words, win.cover_data
    )


def test_lookup_child_rejects_invalid_query_without_network(tmp_path):
    with pytest.raises(AppError, match="название"):
        run_lookup("search", tmp_path, {"query": ""}, Cancellation())
