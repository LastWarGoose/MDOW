import json
from pathlib import Path

from app.adapters.process import run_process, worker_command
from app.models.task import AppError, Tags
from app.services.validation import MAX_BYTES, check_space, youtube_url


class YouTube:
    def download(self, url, directory, cancel, metadata, progress, downloading):
        url = youtube_url(url)
        check_space(directory, MAX_BYTES * 2)
        result = None

        def event(line):
            nonlocal result
            try:
                data = json.loads(line)
            except ValueError:
                return
            kind = data.get("event")
            if kind == "metadata":
                metadata(Tags(title=data["title"], artist=data["artist"], album=data["album"]))
            elif kind == "progress":
                progress(data["percent"])
            elif kind == "downloading":
                downloading()
            elif kind == "error":
                raise AppError(data["message"])
            elif kind == "result":
                result = (directory / data["filename"]).resolve()

        def tick():
            total = sum(p.stat().st_size for p in directory.iterdir() if p.is_file())
            if total > MAX_BYTES:
                raise AppError("Размер загрузки превысил 500 МБ.")
            check_space(directory, 0)

        prefix = worker_command("youtube")
        run_process(prefix + [url, str(directory)], cancel, on_line=event, tick=tick, timeout=1800)
        if result is None or result.parent != Path(directory).resolve() or not result.is_file():
            raise AppError("Загрузчик не вернул аудиофайл.")
        return result
