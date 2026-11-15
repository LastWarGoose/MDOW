"""Restricted yt-dlp entry point. JSON events never contain signed URLs or raw errors."""

import json
import sys
import time
from pathlib import Path

from app.adapters.ffmpeg import find_tool
from app.adapters.network import install_guard
from app.models.task import AppError
from app.services.validation import MAX_BYTES, check_duration, check_space, youtube_url


def emit(kind, **payload):
    print(json.dumps({"event": kind, **payload}, ensure_ascii=True), flush=True)


class QuietLogger:
    def debug(self, message):
        pass

    info = warning = error = debug


def validate_info(info):
    if (
        info.get("_type", "video") != "video"
        or info.get("is_live")
        or info.get("live_status") in {"is_live", "is_upcoming", "post_live"}
    ):
        raise AppError("Плейлисты и трансляции не поддерживаются.")
    if info.get("availability") not in (None, "public", "unlisted") or info.get("age_limit", 0) > 0:
        raise AppError("Ролик ограничен для просмотра. Обход ограничений не поддерживается.")
    check_duration(info.get("duration"))
    if info.get("filesize", 0) and info["filesize"] > MAX_BYTES:
        raise AppError("Размер аудиодорожки превышает 500 МБ.")


def download(url, directory):
    import yt_dlp

    from app.adapters.youtube_policy import RestrictedYoutubeIE

    directory = Path(directory).resolve(strict=True)
    url = youtube_url(url)
    deno = find_tool("deno")
    last_event = 0.0

    def progress(data):
        nonlocal last_event
        downloaded = data.get("downloaded_bytes", 0)
        total = data.get("total_bytes") or data.get("total_bytes_estimate")
        if downloaded > MAX_BYTES or (total and total > MAX_BYTES):
            raise AppError("Размер загрузки превысил 500 МБ.")
        check_space(directory, 0)
        if time.monotonic() - last_event > 0.2 or data.get("status") == "finished":
            emit("progress", percent=min(100, int(downloaded * 100 / total)) if total else -1)
            last_event = time.monotonic()

    def match_filter(info, *, incomplete=False):
        if not incomplete:
            validate_info(info)

    options = {
        "quiet": True,
        "no_warnings": True,
        "logger": QuietLogger(),
        "noplaylist": True,
        "cachedir": False,
        "proxy": "",
        "geo_bypass": False,
        "age_limit": 0,
        "allow_unplayable_formats": False,
        "extractor_args": {"youtube": {"player_client": ["default"], "skip": ["hls", "dash"]}},
        "socket_timeout": 20,
        "retries": 0,
        "fragment_retries": 0,
        "extractor_retries": 0,
        "file_access_retries": 0,
        "format": "bestaudio[protocol=https][vcodec=none][has_drm!=true]",
        "outtmpl": str(directory / "source.%(ext)s"),
        "restrictfilenames": True,
        "max_filesize": MAX_BYTES,
        "overwrites": False,
        "continuedl": False,
        "progress_hooks": [progress],
        "match_filter": match_filter,
        "js_runtimes": {"deno": {"path": deno}},
        "remote_components": set(),
        "allowed_extractors": ["youtube"],
        "enable_file_urls": False,
        "writethumbnail": False,
        "writeinfojson": False,
        "nopart": False,
    }
    with yt_dlp.YoutubeDL(options, auto_init=False) as downloader:
        downloader.add_info_extractor(RestrictedYoutubeIE())
        info = downloader.extract_info(url, download=False, ie_key="Youtube")
        validate_info(info)
        emit(
            "metadata",
            title=(info.get("track") or info.get("title") or "")[:10000],
            artist=(info.get("artist") or "")[:10000],
            album=(info.get("album") or "")[:10000],
        )
        emit("downloading")
        downloader.process_info(info)
    files = [p for p in directory.glob("source.*") if p.suffix not in {".part", ".ytdl"}]
    if len(files) != 1 or not 0 < files[0].stat().st_size <= MAX_BYTES:
        raise AppError("Аудиодорожка не загружена или превышает лимит размера.")
    emit("result", filename=files[0].name)


def main(args=None):
    args = args if args is not None else sys.argv[1:]
    install_guard()
    try:
        if len(args) != 2:
            raise AppError("Некорректные параметры загрузки.")
        download(args[0], args[1])
    except AppError as exc:
        emit("error", message=str(exc))
        return 1
    except Exception:
        emit(
            "error",
            message="YouTube не предоставил аудио. Проверьте сеть и доступность ролика. "
            "Ограничения доступа не обходятся; можно импортировать локальный файл.",
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
