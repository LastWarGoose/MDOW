import re
import shutil
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from app.models.task import AppError

MAX_BYTES = 500 * 1024 * 1024
MAX_SECONDS = 7200
RESERVE_BYTES = 64 * 1024 * 1024
HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}


def youtube_url(value: str) -> str:
    try:
        url = urlsplit(value.strip())
        if (
            url.scheme != "https"
            or url.username is not None
            or url.password is not None
            or url.port not in (None, 443)
            or "\\" in value
            or any(ord(c) < 32 for c in value)
        ):
            raise ValueError
        query = parse_qs(url.query, keep_blank_values=True)
        if "list" in query:
            raise AppError("Плейлисты не поддерживаются. Вставьте ссылку на один ролик.")
        if url.hostname == "youtu.be":
            video_id = url.path.removeprefix("/")
        elif url.hostname in HOSTS:
            if url.path == "/watch" and len(query.get("v", [])) == 1:
                video_id = query["v"][0]
            elif re.fullmatch(r"/(shorts|embed)/[A-Za-z0-9_-]{11}", url.path):
                video_id = url.path.rsplit("/", 1)[1]
            else:
                raise ValueError
        else:
            raise ValueError
        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
            raise ValueError
    except ValueError as exc:
        raise AppError("Нужна HTTPS-ссылка YouTube или youtu.be на один ролик.") from exc
    return f"https://www.youtube.com/watch?v={video_id}"


def safe_filename(title: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title).strip(" .")[:120].rstrip(" .")
    if not name:
        name = "Аудиодорожка"
    if name.split(".")[0].upper() in {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(10)),
        *(f"LPT{i}" for i in range(10)),
    }:
        name = f"_{name}"
    return name + ".mp3"


def check_space(directory: Path, needed: int):
    if shutil.disk_usage(directory).free < needed + RESERVE_BYTES:
        raise AppError("Недостаточно свободного места на диске.")


def check_duration(seconds):
    if not isinstance(seconds, (int, float)) or not 0 < seconds <= MAX_SECONDS:
        raise AppError("Допустимо аудио с известной длительностью до 2 часов.")
