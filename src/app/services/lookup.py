import json
import re
from pathlib import Path
from tempfile import TemporaryDirectory

from app.adapters.covers import crop_cover, load_cover_source
from app.adapters.process import run_process, worker_command
from app.models.task import AppError, Cancelled, Tags


def is_search(value):
    """Keep address-like input on the strict URL validation path."""
    return bool(value.strip()) and not re.search(
        r"(^[./~\\]|\\|://|^[\w+.-]+:(?=\S)|^(?:[\w-]+\.)+[\w-]+(?:[/:?#]|\s*$))", value.strip()
    )


def run_lookup(mode, folder, request, cancel):
    (folder / "request.json").write_text(json.dumps(request), encoding="utf-8")

    def handle_event(line):
        error = json.loads(line).get("error")
        if error:
            raise AppError(error)

    run_process(
        [*worker_command("lookup"), mode, str(folder)],
        cancel,
        timeout=45,
        on_line=handle_event,
    )
    cancel.check()
    return json.loads((folder / "result.json").read_bytes())


class LookupService:
    def search(self, query, cancel):
        if not 1 <= len(query.strip()) <= 200 or any(ord(c) < 32 for c in query):
            raise AppError("Введите название длиной до 200 символов.")
        with TemporaryDirectory(prefix="mdow-search-") as folder:
            return run_lookup("search", Path(folder), {"query": query}, cancel)

    def enrich(self, url, original, duration, cancel):
        request = dict(url=url, title=original.title, artist=original.artist, duration=duration)
        with TemporaryDirectory(prefix="mdow-tags-") as directory:
            folder = Path(directory)
            data = run_lookup("enrich", folder, request, cancel)
            tags = Tags(**data["tags"])
            tags.validate()
            image = folder / "thumbnail"
            source = cover = None
            if image.is_file():
                try:
                    source = load_cover_source(image, cancel)
                    width, height = source.image.size
                    side = min(width, height)
                    cover = crop_cover(
                        source, ((width - side) // 2, (height - side) // 2, side), cancel
                    )
                except Cancelled:
                    raise
                except AppError:
                    source = None
                    data["issues"].append("Не удалось прочитать обложку видео.")
            return tags, source, cover, data["issues"]
