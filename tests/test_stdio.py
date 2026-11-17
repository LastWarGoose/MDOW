import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.skipif(os.name != "nt", reason="Windows GUI standard streams")
@pytest.mark.parametrize("worker", [False, True])
def test_pythonw_runs_without_console_and_preserves_worker_events(worker):
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    script = f"""
import ctypes
import sys
# Match the stream state of PyInstaller's windowed bootloader.
sys.stdin = sys.stdout = sys.stderr = None
from app.adapters.stdio import configure_stdio
configure_stdio(worker={worker!r})
assert ctypes.windll.kernel32.GetConsoleWindow() == 0
assert sys.stdin.read() == ''
sys.stderr.write('discarded diagnostic')
from app.adapters.youtube_worker import emit
emit('metadata', title='Тест обложки', percent=42)
"""
    result = subprocess.run(
        [str(pythonw), "-c", script],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        creationflags=subprocess.CREATE_NO_WINDOW,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    if worker:
        assert json.loads(result.stdout) == {
            "event": "metadata",
            "title": "Тест обложки",
            "percent": 42,
        }
    else:
        assert result.stdout == ""
