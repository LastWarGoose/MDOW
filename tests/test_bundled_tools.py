import sys

import pytest

from app.adapters import ffmpeg


@pytest.mark.parametrize("external_override", [False, True])
def test_frozen_tool_lookup(tmp_path, monkeypatch, external_override):
    external = tmp_path / "Desktop"
    bundle = tmp_path / "extracted app"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
    monkeypatch.setattr(ffmpeg, "project_root", lambda: external)
    bundled_tool = bundle / "tools/bin/ffmpeg.exe"
    bundled_tool.parent.mkdir(parents=True)
    bundled_tool.touch()
    expected = bundled_tool
    if external_override:
        expected = external / "tools/bin/ffmpeg.exe"
        expected.parent.mkdir(parents=True)
        expected.touch()
    assert ffmpeg.find_tool("ffmpeg") == str(expected)
