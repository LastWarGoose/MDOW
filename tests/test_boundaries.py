import json
import os
import socket
import sys
import time
from io import BytesIO

import pytest
from PIL import Image

from app.adapters import youtube_worker
from app.adapters.network import install_guard
from app.adapters.process import run_process
from app.adapters.tags import TagAdapter
from app.models.task import AppError, Cancellation, Tags
from app.services.workspace import Workspace, cleanup_stale


def test_socket_guard_blocks_direct_and_rebound_connections():
    script = """
import socket
from app.adapters.network import install_guard
from app.models.task import AppError
install_guard()
for address in [('127.0.0.1', 80), ('169.254.169.254', 80), ('localhost', 80)]:
    try:
        with socket.socket() as connection:
            connection.connect(address)
    except AppError:
        continue
    raise RuntimeError('Guard failed')
print('blocked')
"""
    assert run_process([sys.executable, "-c", script], Cancellation()).strip() == "blocked"


def test_dns_guard_rejects_mixed_public_private_answers(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
        ],
    )
    monkeypatch.setattr(sys, "addaudithook", lambda _: None)
    install_guard()
    with pytest.raises(AppError):
        socket.getaddrinfo("example.org", 443)


def test_downloader_is_audio_only_and_emits_metadata_first(monkeypatch, tmp_path, capsys):
    captured = {}

    class FakeDownloader:
        def __init__(self, options, auto_init):
            captured.update(options)
            assert auto_init is False

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def add_info_extractor(self, extractor):
            assert extractor.IE_NAME == "youtube"

        def extract_info(self, url, **kwargs):
            assert kwargs == {"download": False, "ie_key": "Youtube"}
            return {"title": "Название", "channel": "Не исполнитель", "duration": 10}

        def process_info(self, info):
            (tmp_path / "source.m4a").write_bytes(b"test audio")
            captured["progress_hooks"][0](
                {"downloaded_bytes": 10, "total_bytes": 10, "status": "finished"}
            )

    monkeypatch.setattr("yt_dlp.YoutubeDL", FakeDownloader)
    monkeypatch.setattr(youtube_worker, "find_tool", lambda _: "deno")
    youtube_worker.download("https://youtu.be/abcdefgh_-1", tmp_path)
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [x["event"] for x in events] == ["metadata", "downloading", "progress", "result"]
    assert events[0]["artist"] == ""
    assert captured["format"] == "bestaudio[protocol=https][vcodec=none][has_drm!=true]"
    assert captured["allowed_extractors"] == ["youtube"]
    assert captured["geo_bypass"] is False
    assert captured["proxy"] == ""
    assert captured["retries"] == 0
    assert not captured["remote_components"]
    assert captured["extractor_args"]["youtube"] == {
        "player_client": ["default"],
        "skip": ["hls", "dash"],
    }


@pytest.mark.parametrize("status", ["LOGIN_REQUIRED", "UNPLAYABLE", "AGE_CHECK_REQUIRED", "ERROR"])
def test_restrictions_stop_before_fallback_clients(status):
    from app.adapters.youtube_policy import RestrictedYoutubeIE

    extractor = RestrictedYoutubeIE()
    with pytest.raises(AppError):
        extractor._invalid_player_response({"playabilityStatus": {"status": status}}, "abcdefgh_-1")


def test_no_age_verification_parameters(monkeypatch):
    from app.adapters.youtube_policy import RestrictedYoutubeIE

    extractor = RestrictedYoutubeIE()
    calls = []
    monkeypatch.setattr(
        extractor, "_download_webpage_with_retries", lambda *a, **kw: calls.append((a, kw))
    )
    extractor._download_initial_webpage(
        "https://www.youtube.com/watch?v=abcdefgh_-1", "web", "abcdefgh_-1"
    )
    assert calls[0][1] == {}
    with pytest.raises(AppError):
        extractor._is_agegated({"playabilityStatus": {"reason": "confirm your age"}})


def test_atomic_publish_does_not_clobber_racing_file(mp3, tmp_path, monkeypatch):
    destination = tmp_path / "racing.mp3"
    tagger = TagAdapter()
    real_write = tagger.write

    def race(*args):
        real_write(*args)
        destination.write_bytes(b"created by another application")

    monkeypatch.setattr(tagger, "write", race)
    with pytest.raises(FileExistsError):
        tagger.save(mp3, destination, Tags(title="test"), Cancellation())
    assert destination.read_bytes() == b"created by another application"
    assert not list(tmp_path.glob(".mdow-save-*"))


def test_failed_verification_preserves_source(mp3, monkeypatch):
    original = mp3.read_bytes()
    tagger = TagAdapter()
    monkeypatch.setattr(tagger, "read", lambda _: Tags(title="wrong"))
    with pytest.raises(AppError, match="Проверка"):
        tagger.save(mp3, mp3, Tags(title="right"), Cancellation(), overwrite=True)
    assert mp3.read_bytes() == original


def test_cover_replacement_has_one_front_cover(mp3, tmp_path):
    from mutagen.id3 import ID3

    tagger = TagAdapter()
    for color in ("red", "blue"):
        image = BytesIO()
        Image.new("RGB", (40, 40), color).save(image, "PNG")
        tagger.save(mp3, mp3, Tags(cover=image.getvalue()), Cancellation(), overwrite=True)
    covers = ID3(mp3).getall("APIC")
    assert len(covers) == 1
    assert covers[0].type == 3
    with Image.open(BytesIO(covers[0].data)) as picture:
        assert picture.getpixel((10, 10))[2] > 240


def test_stale_cleanup_keeps_active_and_unowned(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.workspace.root", lambda: tmp_path)
    active = Workspace()
    stale = Workspace()
    stale._lock.close()  # Simulate a crashed process; keep the files.
    unowned = tmp_path / "someone-elses-files"
    unowned.mkdir()
    (unowned / "keep").write_text("keep")
    for directory in (active.path, stale.path):
        os.utime(directory / ".mdow-owner", (time.time() - 100000,) * 2)
    try:
        cleanup_stale()
        assert active.path.exists()
        assert not stale.path.exists()
        assert (unowned / "keep").read_text() == "keep"
    finally:
        active.close()
