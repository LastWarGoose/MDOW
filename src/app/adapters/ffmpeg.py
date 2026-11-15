import json
import os
import shutil
import sys
from pathlib import Path

from app.adapters.process import run_process
from app.models.task import AppError
from app.services.validation import MAX_BYTES, check_duration, check_space


def project_root():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parents[3]


def find_tool(name):
    suffix = ".exe" if os.name == "nt" else ""
    local = project_root() / "tools" / "bin" / (name + suffix)
    if local.is_file():
        return str(local)
    if getattr(sys, "frozen", False):
        bundled = Path(sys._MEIPASS) / "tools" / "bin" / (name + suffix)
        if bundled.is_file():
            return str(bundled)
    found = shutil.which(name)
    if found:
        return found
    raise AppError(f"Не найден {name}. Установите его в tools/bin или добавьте в PATH.")


class FFmpeg:
    def __init__(self, ffmpeg=None, ffprobe=None):
        self.ffmpeg = ffmpeg
        self.ffprobe = ffprobe

    def check(self, cancel):
        self.ffmpeg = self.ffmpeg or find_tool("ffmpeg")
        self.ffprobe = self.ffprobe or find_tool("ffprobe")
        versions = []
        for tool in (self.ffmpeg, self.ffprobe):
            versions.append(run_process([tool, "-version"], cancel, timeout=10).splitlines()[0])
        encoders = run_process([self.ffmpeg, "-hide_banner", "-encoders"], cancel, timeout=10)
        if "libmp3lame" not in encoders:
            raise AppError("Эта сборка FFmpeg не содержит кодировщик libmp3lame.")
        return versions

    def probe(self, path, cancel):
        if not self.ffprobe:
            self.check(cancel)
        text = run_process(
            [
                self.ffprobe,
                "-v",
                "error",
                "-protocol_whitelist",
                "file,pipe",
                "-show_entries",
                "format=duration,format_name:stream=codec_name,codec_type",
                "-of",
                "json",
                str(path),
            ],
            cancel,
            timeout=30,
        )
        try:
            data = json.loads(text)
            duration = float(data["format"]["duration"])
            check_duration(duration)
            audio = [s for s in data["streams"] if s["codec_type"] == "audio"]
            if not audio:
                raise ValueError
            return duration, audio[0]["codec_name"]
        except (KeyError, ValueError, TypeError) as exc:
            raise AppError("Файл не содержит пригодную аудиодорожку.") from exc

    def convert(self, source, target, cancel, progress):
        duration, _ = self.probe(source, cancel)
        check_space(target.parent, MAX_BYTES)

        def line(value):
            if value.startswith("out_time_us="):
                try:
                    progress(min(99, int(int(value.split("=", 1)[1]) / duration / 10_000)))
                except ValueError:
                    pass

        def tick():
            if target.exists() and target.stat().st_size > MAX_BYTES:
                raise AppError("Размер MP3 превысил 500 МБ.")
            check_space(target.parent, 0)

        try:
            run_process(
                [
                    self.ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-nostdin",
                    "-n",
                    "-protocol_whitelist",
                    "file,pipe",
                    "-i",
                    source,
                    "-map",
                    "0:a:0",
                    "-vn",
                    "-sn",
                    "-dn",
                    "-map_metadata",
                    "-1",
                    "-c:a",
                    "libmp3lame",
                    "-q:a",
                    "2",
                    "-progress",
                    "pipe:1",
                    target,
                ],
                cancel,
                on_line=line,
                tick=tick,
            )
            _, codec = self.probe(target, cancel)
            if codec != "mp3":
                raise AppError("Результат конвертации не является MP3.")
            progress(100)
        except Exception:
            target.unlink(missing_ok=True)
            raise
