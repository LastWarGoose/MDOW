"""Bounded HTTPS requests in a cancellable child with the downloader's network guard."""

import json
import re
import sys
from http.client import HTTPException, HTTPSConnection
from pathlib import Path
from urllib.parse import urlencode

from app.adapters.covers import MAX_COVER_SOURCE
from app.adapters.network import install_guard
from app.models.task import AppError
from app.services.validation import youtube_url

USER_AGENT = "MDOW/0.1.0 (https://github.com/LastWarGoose/MDOW)"


class ServiceError(AppError):
    def __init__(self, status):
        super().__init__("Сервис временно недоступен.")
        self.status = status


def fetch(host, path, *, limit=2_000_000):
    connection = HTTPSConnection(host, timeout=8)
    try:
        connection.request("GET", path, headers={"User-Agent": USER_AGENT})
        with connection.getresponse() as response:
            if response.status != 200:
                raise ServiceError(response.status)
            data = response.read(limit + 1)
            if len(data) > limit:
                raise AppError("Ответ сервиса превышает допустимый размер.")
            return data
    except (OSError, HTTPException) as exc:
        raise AppError("Не удалось подключиться к сервису. Проверьте подключение к сети.") from exc
    finally:
        connection.close()


def search(query):
    from yt_dlp import YoutubeDL
    from yt_dlp.extractor.youtube import YoutubeSearchIE
    from yt_dlp.utils import DownloadError, ExtractorError

    from app.adapters.youtube_worker import QuietLogger

    if not isinstance(query, str) or not 1 <= len(query.strip()) <= 200 or not query.isprintable():
        raise AppError("Введите название длиной до 200 символов.")
    options = {
        "quiet": True,
        "logger": QuietLogger(),
        "cachedir": False,
        "proxy": "",
        "geo_bypass": False,
        "extract_flat": True,
        "skip_download": True,
        "retries": 0,
        "extractor_retries": 0,
        "socket_timeout": 12,
    }
    try:
        with YoutubeDL(options, auto_init=False) as client:
            client.add_info_extractor(YoutubeSearchIE())
            result = client.extract_info(
                f"ytsearch5:{query}", ie_key=YoutubeSearchIE.ie_key(), download=False, process=False
            )
            return video_choices(result["entries"])
    except (DownloadError, ExtractorError, OSError) as exc:
        raise AppError(
            "Поиск YouTube сейчас недоступен. Повторите позже или вставьте ссылку на ролик."
        ) from exc


def video_choices(entries):
    choices = []
    for item in entries:
        if not item or item.get("ie_key") != "Youtube":
            continue
        video_id = item.get("id") or ""
        if not re.fullmatch(r"[a-zA-Z0-9_-]{11}", video_id) or not item.get("title"):
            continue
        if item.get("live_status") in ("is_live", "is_upcoming", "post_live") or item.get(
            "is_live"
        ):
            continue
        choices.append(
            dict(
                url=youtube_url("https://youtu.be/" + video_id),
                title=item["title"][:500],
                channel=(item.get("channel") or item.get("uploader") or "")[:250],
                duration=item.get("duration"),
            )
        )
    return choices


def normalized(value):
    return " ".join(re.findall(r"[^\W_]+", value.casefold()))


def lookup_track(title, artist, duration):
    # Strip presentation labels only. Live, remixes and covers are distinct versions.
    title = re.sub(
        r"\s*[\[(](?:official (?:music )?(?:video|audio)|lyrics? video|официальный клип)[\])]\s*$",
        "",
        title,
        flags=re.I,
    ).strip()
    parts = re.split(r"\s+[–—-]\s+", title, maxsplit=1)
    if len(parts) == 2 and (not artist or normalized(parts[0]) == normalized(artist)):
        artist, title = parts
    params = {"track_name": title}
    if artist:
        params["artist_name"] = artist
    records = json.loads(fetch("lrclib.net", "/api/search?" + urlencode(params)))
    matches = []
    identity = {}
    for row in records:
        song, performer, length = row.get("trackName"), row.get("artistName"), row.get("duration")
        if not isinstance(song, str) or not isinstance(performer, str) or not performer.strip():
            continue
        if normalized(song) != normalized(title) or (
            artist and normalized(performer) != normalized(artist)
        ):
            continue
        if artist:
            identity = dict(title=song[:10000], artist=performer[:10000])
        if isinstance(length, (int, float)) and abs(length - duration) <= 2:
            matches.append(row)
    if len({normalized(r["artistName"]) for r in matches}) != 1:
        return identity
    best = min(matches, key=lambda row: abs(row["duration"] - duration))
    lyrics = best.get("plainLyrics")
    return dict(
        title=best["trackName"][:10000],
        artist=best["artistName"][:10000],
        album=(best.get("albumName") or "")[:10000],
        lyrics=lyrics
        if isinstance(lyrics, str) and len(lyrics) <= 100000 and not best.get("instrumental")
        else "",
    )


def thumbnail(video_id):
    prefix = f"/vi/{video_id}/"
    try:
        return fetch("i.ytimg.com", prefix + "maxresdefault.jpg", limit=MAX_COVER_SOURCE)
    except ServiceError as exc:
        if exc.status != 404:
            raise
    return fetch("i.ytimg.com", prefix + "hqdefault.jpg", limit=MAX_COVER_SOURCE)


def enrich(request, folder):
    video_id = youtube_url(request["url"]).split("v=")[1]
    issues = []
    tags = {}
    try:
        tags = lookup_track(request["title"], request["artist"], request["duration"])
        if not tags.get("lyrics"):
            issues.append("Точное совпадение для текста песни не найдено.")
    except (AppError, ValueError, TypeError, KeyError, AttributeError):
        issues.append("Не удалось получить данные из LRCLIB.")
    try:
        image = thumbnail(video_id)
        (folder / "thumbnail").write_bytes(image)
    except AppError:
        issues.append("Не удалось загрузить обложку видео.")
    return {"tags": tags, "issues": issues}


def main(args=None):
    args = sys.argv[1:] if args is None else args
    install_guard()
    try:
        mode, directory = args
        folder = Path(directory)
        request = json.loads((folder / "request.json").read_bytes())
        if mode == "search":
            result = search(request["query"])
        elif mode == "enrich":
            result = enrich(request, folder)
        else:
            raise AppError("Неизвестная операция поиска.")
        (folder / "result.json").write_text(
            json.dumps(result, ensure_ascii=False), encoding="utf-8"
        )
    except (AppError, ValueError, OSError, KeyError, TypeError) as exc:
        message = str(exc) if isinstance(exc, AppError) else "Не удалось прочитать ответ сервиса."
        print(json.dumps({"error": message}), flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
