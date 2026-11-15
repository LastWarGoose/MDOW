"""Explicit installation of pinned external Windows tools, with SHA-256 verification."""

import argparse
import hashlib
import shutil
import tempfile
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

TOOLS = {
    "ffmpeg": {
        "version": "8.0.1-essentials_build",
        "url": "https://github.com/GyanD/codexffmpeg/releases/download/8.0.1/ffmpeg-8.0.1-essentials_build.zip",
        "sha256": "e2aaeaa0fdbc397d4794828086424d4aaa2102cef1fb6874f6ffd29c0b88b673",
        "executables": {"ffmpeg.exe", "ffprobe.exe"},
    },
    "deno": {
        "version": "2.9.8",
        "url": "https://github.com/denoland/deno/releases/download/v2.9.8/deno-x86_64-pc-windows-msvc.zip",
        "sha256": "cba84b26e0df5ae7f74fc66b86a95b866872a86292ebd84fa1e959927edd93bf",
        "executables": {"deno.exe"},
    },
}


def download(url, destination):
    # Small ranges avoid stalled large responses on some networks. Total concurrency is bounded.
    request = urllib.request.Request(url, headers={"Range": "bytes=0-0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        content_range = response.headers.get("Content-Range")
        if not content_range:
            with destination.open("wb") as stream:
                shutil.copyfileobj(response, stream, length=1024 * 1024)
            return
        size = int(content_range.split("/")[-1])
    with destination.open("wb") as stream:
        stream.truncate(size)

    def chunk(start):
        end = min(start + 1024 * 1024, size) - 1
        request = urllib.request.Request(url, headers={"Range": f"bytes={start}-{end}"})
        with urllib.request.urlopen(request, timeout=60) as response:
            if response.status != 206:
                raise RuntimeError("Сервер не поддержал частичную загрузку.")
            data = response.read(end - start + 2)
        if len(data) != end - start + 1:
            raise RuntimeError("Получена неполная часть архива.")
        with destination.open("r+b") as stream:
            stream.seek(start)
            stream.write(data)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(chunk, range(0, size, 1024 * 1024)))


def install(name, settings, target):
    print(f"Установка {name} {settings['version']}…", flush=True)
    with tempfile.TemporaryDirectory(prefix="mdow-tools-") as folder:
        archive_path = Path(folder) / "download.zip"
        download(settings["url"], archive_path)
        with archive_path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != settings["sha256"]:
            raise RuntimeError("Контрольная сумма архива не совпала. Установка прервана.")
        found = set()
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.infolist():
                filename = Path(member.filename).name
                if filename in settings["executables"]:
                    with archive.open(member) as source, (target / filename).open("wb") as output:
                        shutil.copyfileobj(source, output, length=1024 * 1024)
                    found.add(filename)
                elif filename.lower().startswith(("license", "copying", "notice")):
                    notices = target / "licenses" / name
                    notices.mkdir(parents=True, exist_ok=True)
                    (notices / filename).write_bytes(archive.read(member))
        if found != settings["executables"]:
            raise RuntimeError("В архиве отсутствуют необходимые инструменты.")
    print(f"Готово: {name}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ffmpeg-only", action="store_true")
    parser.add_argument(
        "--target", type=Path, default=Path(__file__).resolve().parents[1] / "tools" / "bin"
    )
    args = parser.parse_args()
    args.target.mkdir(parents=True, exist_ok=True)
    for name, settings in TOOLS.items():
        if args.ffmpeg_only and name != "ffmpeg":
            continue
        install(name, settings, args.target)


if __name__ == "__main__":
    main()
