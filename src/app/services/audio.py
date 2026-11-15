from dataclasses import replace
from pathlib import Path

from app.adapters.covers import prepare_cover
from app.adapters.ffmpeg import FFmpeg
from app.adapters.tags import TagAdapter, copy_stream
from app.adapters.youtube import YouTube
from app.models.task import AppError, Cancelled, State, Tags, TaskState
from app.services.validation import MAX_BYTES, check_space
from app.services.workspace import Workspace, cleanup_stale


class AudioService:
    def __init__(self, converter=None, tagger=None, downloader=None):
        self.converter = converter or FFmpeg()
        self.tagger = tagger or TagAdapter()
        self.downloader = downloader or YouTube()
        self.state = TaskState()
        self.workspace = None
        self.audio = None

    def startup(self, cancel):
        cleanup_stale()
        return self.converter.check(cancel)

    def close(self):
        if self.workspace:
            self.workspace.close()
            self.workspace = None
        self.audio = None

    def prepare(self, source, is_url, cancel, notify, metadata):
        def state(value):
            self.state.move(value)
            notify(value, -1)

        try:
            self.close()
            state(State.CHECKING)
            self.converter.check(cancel)
            cancel.check()
            self.workspace = Workspace()
            folder = self.workspace.path
            if is_url:
                download_dir = folder / "download"
                download_dir.mkdir()
                source = self.downloader.download(
                    source,
                    download_dir,
                    cancel,
                    metadata,
                    lambda n: notify(State.DOWNLOADING, n),
                    lambda: state(State.DOWNLOADING),
                )
                values = None
            else:
                source = Path(source).resolve(strict=True)
                if not source.is_file() or not 0 < source.stat().st_size <= MAX_BYTES:
                    raise AppError("Выберите непустой аудиофайл размером не больше 500 МБ.")
                values = Tags(title=source.stem)
            duration, codec = self.converter.probe(source, cancel)
            target = folder / "working.mp3"
            if codec == "mp3" and not is_url:
                check_space(folder, source.stat().st_size)
                copy_stream(source, target, cancel)
                values = self.tagger.read(target)
                if values.cover:
                    values = replace(values, cover=prepare_cover(values.cover))
            else:
                if values:
                    metadata(values)
                state(State.CONVERTING)
                self.converter.convert(
                    source, target, cancel, lambda n: notify(State.CONVERTING, n)
                )
            cancel.check()
            if codec == "mp3" and not is_url:
                metadata(values)
            self.audio = target
            state(State.EDITING)
            return {"path": target, "duration": duration}
        except Exception as exc:
            self.close()
            state(State.CANCELLED if isinstance(exc, Cancelled) else State.ERROR)
            raise

    def save(self, destination, values, cancel, notify, *, overwrite=False):
        if not self.audio:
            raise AppError("Сначала загрузите или импортируйте аудио.")
        try:
            self.state.move(State.SAVING)
            notify(State.SAVING, -1)
            path = self.tagger.save(self.audio, destination, values, cancel, overwrite=overwrite)
            self.state.move(State.COMPLETED)
            notify(State.COMPLETED, 100)
            return path
        except Exception as exc:
            target = State.CANCELLED if isinstance(exc, Cancelled) else State.ERROR
            self.state.move(target)
            notify(target, 0)
            raise
