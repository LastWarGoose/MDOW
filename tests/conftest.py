import math
import struct
import wave

import pytest

from app.adapters.ffmpeg import FFmpeg
from app.models.task import Cancellation


@pytest.fixture
def tone(tmp_path):
    path = tmp_path / "синтетический тон.wav"
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(22050)
        samples = (int(4000 * math.sin(2 * math.pi * 440 * n / 22050)) for n in range(22050))
        audio.writeframes(b"".join(struct.pack("<h", sample) for sample in samples))
    return path


@pytest.fixture
def converter():
    adapter = FFmpeg()
    adapter.check(Cancellation())
    return adapter


@pytest.fixture
def mp3(tone, tmp_path, converter):
    output = tmp_path / "original.mp3"
    converter.convert(tone, output, Cancellation(), lambda n: None)
    return output
