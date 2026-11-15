import sys
import threading
import time
from dataclasses import replace
from io import BytesIO

import pytest
from mutagen.id3 import ID3, TCOM
from PIL import Image

from app.adapters.covers import prepare_cover
from app.adapters.ffmpeg import FFmpeg
from app.adapters.process import run_process
from app.adapters.tags import TagAdapter
from app.models.task import AppError, Cancellation, Cancelled, State, Tags
from app.services.audio import AudioService


def packet_hash(path, converter):
    return run_process(
        [
            converter.ffmpeg,
            "-v",
            "error",
            "-i",
            path,
            "-map",
            "0:a:0",
            "-c:a",
            "copy",
            "-f",
            "hash",
            "-hash",
            "sha256",
            "-",
        ],
        Cancellation(),
    )


def test_conversion_and_tag_roundtrip(mp3, converter, tmp_path):
    duration, codec = converter.probe(mp3, Cancellation())
    assert codec == "mp3"
    assert 0.9 < duration < 1.2
    tagger = TagAdapter()
    existing = ID3(mp3)
    existing.add(TCOM(encoding=1, text=["Композитор"]))
    existing.save(mp3)
    original = mp3.read_bytes()
    picture = BytesIO()
    Image.new("RGB", (50, 50), "blue").save(picture, "PNG")
    cover = prepare_cover(picture.getvalue())
    tags = Tags("Песня", "Исполнитель", "Альбом", "Первая строка\nВторая строка\n", cover)
    result = tmp_path / "готово.mp3"
    tagger.save(mp3, result, tags, Cancellation())
    read = tagger.read(result)
    assert replace(read, cover=cover) == tags
    assert ID3(result).version == (2, 3, 0)
    assert str(ID3(result)["TCOM"]) == "Композитор"
    assert mp3.read_bytes() == original
    assert packet_hash(mp3, converter) == packet_hash(result, converter)
    for key in ("TIT2", "TPE1", "TALB", "USLT", "APIC"):
        assert len(ID3(result).getall(key)) == 1
        assert ID3(result).getall(key)[0].encoding == 1
    replacement = replace(tags, title="Другое название", lyrics="Новый текст")
    tagger.save(result, result, replacement, Cancellation(), overwrite=True)
    assert tagger.read(result).lyrics == "Новый текст"
    tagger.save(result, result, Tags(), Cancellation(), overwrite=True)
    assert tagger.read(result) == Tags()
    assert str(ID3(result)["TCOM"]) == "Композитор"
    assert packet_hash(mp3, converter) == packet_hash(result, converter)


def test_save_conflict_and_failure(mp3, tmp_path, monkeypatch):
    destination = tmp_path / "existing.mp3"
    destination.write_bytes(b"keep me")
    tagger = TagAdapter()
    with pytest.raises(AppError, match="существует"):
        tagger.save(mp3, destination, Tags(), Cancellation())

    def fail(*_):
        raise PermissionError

    monkeypatch.setattr(tagger, "write", fail)
    with pytest.raises(PermissionError):
        tagger.save(mp3, destination, Tags(), Cancellation(), overwrite=True)
    assert destination.read_bytes() == b"keep me"
    assert not list(tmp_path.glob(".mdow-save-*"))


def test_cancel_during_save(mp3, tmp_path, monkeypatch):
    tagger = TagAdapter()
    destination = tmp_path / "cancelled.mp3"
    destination.write_bytes(b"keep me")
    token = Cancellation()
    real_write = tagger.write

    def write_and_cancel(*args):
        real_write(*args)
        token.cancel()

    monkeypatch.setattr(tagger, "write", write_and_cancel)
    with pytest.raises(Cancelled):
        tagger.save(mp3, destination, Tags(title="test"), token, overwrite=True)
    assert destination.read_bytes() == b"keep me"
    assert not list(tmp_path.glob(".mdow-save-*"))


def test_process_cancel():
    token = Cancellation()
    timer = threading.Timer(0.3, token.cancel)
    timer.start()
    started = time.monotonic()
    with pytest.raises(Cancelled):
        run_process([sys.executable, "-c", "import time; time.sleep(60)"], token)
    timer.join()
    assert time.monotonic() - started < 10


def test_missing_ffmpeg(monkeypatch):
    def missing(_):
        raise AppError("Не найден ffmpeg")

    monkeypatch.setattr("app.adapters.ffmpeg.find_tool", missing)
    with pytest.raises(AppError, match="ffmpeg"):
        FFmpeg().check(Cancellation())


def test_local_workflow(tone, converter, tmp_path):
    service = AudioService(converter=converter)
    events, metadata = [], []
    try:
        result = service.prepare(
            tone, False, Cancellation(), lambda s, p: events.append(s), metadata.append
        )
        assert result["path"].exists()
        assert metadata[0].title == tone.stem
        assert State.CONVERTING in events
        output = service.save(
            tmp_path / "saved.mp3", Tags(title="Трек"), Cancellation(), lambda *_: None
        )
        assert service.tagger.read(output).title == "Трек"
        assert service.state.current == State.COMPLETED
    finally:
        workspace = service.workspace.path if service.workspace else None
        service.close()
    assert workspace and not workspace.exists()


@pytest.mark.parametrize("cancelled", [False, True])
def test_download_failure_cleans_workspace(converter, cancelled):
    class FailingDownloader:
        def download(self, url, directory, cancel, metadata, progress, downloading):
            downloading()
            (directory / "source.part").write_bytes(b"partial")
            if cancelled:
                cancel.cancel()
                cancel.check()
            raise AppError("Сетевая ошибка")

    service = AudioService(converter=converter, downloader=FailingDownloader())
    with pytest.raises(Cancelled if cancelled else AppError):
        service.prepare("url", True, Cancellation(), lambda *_: None, lambda _: None)
    assert service.workspace is None
    assert service.audio is None
    assert service.state.current == (State.CANCELLED if cancelled else State.ERROR)


def test_cancel_conversion(tone, converter, tmp_path):
    token = Cancellation()
    target = tmp_path / "partial.mp3"

    def progress(_):
        token.cancel()

    with pytest.raises(Cancelled):
        converter.convert(tone, target, token, progress)
    assert not target.exists()
