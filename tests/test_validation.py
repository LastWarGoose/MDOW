from io import BytesIO

import pytest
from PIL import Image

from app.adapters.covers import prepare_cover
from app.adapters.network import public_address
from app.adapters.youtube_worker import validate_info
from app.models.task import AppError, Cancellation, Cancelled, State, Tags, TaskState
from app.services.validation import check_duration, check_space, safe_filename, youtube_url


@pytest.mark.parametrize(
    "url",
    [
        "https://youtu.be/abcdefgh_-1?t=4",
        "https://www.youtube.com/watch?v=abcdefgh_-1",
        "https://m.youtube.com/shorts/abcdefgh_-1",
        "https://music.youtube.com/watch?v=abcdefgh_-1",
        "https://youtube.com/embed/abcdefgh_-1",
    ],
)
def test_canonical_url(url):
    assert youtube_url(url) == "https://www.youtube.com/watch?v=abcdefgh_-1"


@pytest.mark.parametrize(
    "url",
    [
        "http://youtu.be/abcdefgh_-1",
        "https://youtube.com.evil.org/watch?v=abcdefgh_-1",
        "https://youtube.com@127.0.0.1/watch?v=abcdefgh_-1",
        "file:///a.mp3",
        "https://youtu.be/abcdefgh_-1?list=PL",
        "https://youtube.com/watch?v=abcdefgh_-1&v=abcdefgh_-1",
        "https://youtu.be/short",
        "https://youtu.be:99/abcdefgh_-1",
        "https://youtu.be:bad/abcdefgh_-1",
        "https://youtu.be/abcdefgh_-1/other",
        "https://youtube.com/live/abcdefgh_-1",
        "https://youtu.be/abcdefgh_-1\n",
        "https://user:pass@youtu.be/abcdefgh_-1",
    ],
)
def test_reject_url(url):
    with pytest.raises(AppError):
        youtube_url(url)


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "169.254.169.254",
        "::1",
        "::ffff:127.0.0.1",
        "fc00::1",
        "192.168.1.1",
        "224.0.0.1",
        "localhost",
        "100.64.1.1",
    ],
)
def test_network_private_addresses(address):
    assert not public_address(address)


def test_network_public_addresses():
    assert public_address("8.8.8.8")
    assert public_address("2606:4700:4700::1111")


def test_paths():
    assert safe_filename("CON") == "_CON.mp3"
    assert safe_filename("../../name:bad") == "_.._name_bad.mp3"
    assert safe_filename(" .. ") == "Аудиодорожка.mp3"
    assert len(safe_filename("я" * 500)) < 130


@pytest.mark.parametrize("duration", [None, 0, -1, 7201, float("inf"), float("nan")])
def test_duration(duration):
    with pytest.raises(AppError):
        check_duration(duration)


def test_no_space(monkeypatch, tmp_path):
    from collections import namedtuple

    usage = namedtuple("Usage", "free")
    monkeypatch.setattr("app.services.validation.shutil.disk_usage", lambda _: usage(0))
    with pytest.raises(AppError, match="места"):
        check_space(tmp_path, 1)


def test_cover_limits():
    image = Image.new("RGB", (1800, 1200), "red")
    stream = BytesIO()
    image.save(stream, "PNG")
    cover = prepare_cover(stream.getvalue())
    with Image.open(BytesIO(cover)) as loaded:
        assert loaded.size == (1500, 1000)
        assert loaded.format == "JPEG"
    assert len(cover) <= 2 * 1024 * 1024
    for value in (b"broken", b"x" * (10 * 1024 * 1024 + 1)):
        with pytest.raises(AppError):
            prepare_cover(value)


def test_cover_pixel_limit():
    stream = BytesIO()
    Image.new("1", (5001, 5000)).save(stream, "PNG")
    with pytest.raises(AppError, match="мегапикселей"):
        prepare_cover(stream.getvalue())


def test_tags_limits():
    with pytest.raises(AppError):
        Tags(lyrics="a" * 100001).validate()
    with pytest.raises(AppError):
        Tags(title="x\x00y").validate()


def test_state_machine():
    state = TaskState()
    with pytest.raises(AppError):
        state.move(State.SAVING)
    for value in [
        State.CHECKING,
        State.DOWNLOADING,
        State.CONVERTING,
        State.EDITING,
        State.SAVING,
        State.COMPLETED,
        State.SAVING,
        State.CANCELLED,
        State.SAVING,
    ]:
        state.move(value)
    assert state.current == State.SAVING


def test_cancel():
    token = Cancellation()
    token.cancel()
    with pytest.raises(Cancelled):
        token.check()


@pytest.mark.parametrize(
    "change",
    [
        {"is_live": True},
        {"_type": "playlist"},
        {"availability": "needs_auth"},
        {"age_limit": 18},
        {"duration": 8000},
        {"filesize": 501 * 1024 * 1024},
    ],
)
def test_youtube_limits(change):
    with pytest.raises(AppError):
        validate_info({"duration": 100, **change})
