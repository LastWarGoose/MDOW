import os
import tempfile
from pathlib import Path

from mutagen.id3 import APIC, ID3, TALB, TIT2, TPE1, USLT, ID3NoHeaderError
from mutagen.mp3 import MP3

from app.adapters.covers import prepare_cover
from app.models.task import AppError, Tags
from app.services.validation import MAX_BYTES, check_space


def copy_stream(source, target, cancel):
    with Path(source).open("rb") as incoming, Path(target).open("wb") as outgoing:
        copied = 0
        while chunk := incoming.read(1024 * 1024):
            cancel.check()
            copied += len(chunk)
            if copied > MAX_BYTES:
                raise AppError("Размер аудиофайла превысил 500 МБ.")
            check_space(Path(target).parent, len(chunk))
            outgoing.write(chunk)
        outgoing.flush()
        os.fsync(outgoing.fileno())
    cancel.check()


class TagAdapter:
    def read(self, path):
        try:
            tags = ID3(path, v2_version=3)
        except ID3NoHeaderError:
            return Tags()

        def value(key):
            frame = tags.get(key)
            return str(frame) if frame else ""

        lyrics = tags.getall("USLT")
        pictures = tags.getall("APIC")
        front = next((p for p in pictures if p.type == 3), None)
        cover = front or (pictures[0] if pictures else None)
        return Tags(
            value("TIT2"),
            value("TPE1"),
            value("TALB"),
            lyrics[0].text if lyrics else "",
            cover.data if cover else None,
        )

    def write(self, path, values):
        values.validate()
        try:
            tags = ID3(path, v2_version=3)
        except ID3NoHeaderError:
            tags = ID3()
        for key in ("TIT2", "TPE1", "TALB", "USLT", "APIC"):
            tags.delall(key)
        for frame, value in ((TIT2, values.title), (TPE1, values.artist), (TALB, values.album)):
            if value:
                tags.add(frame(encoding=1, text=[value]))
        if values.lyrics:
            tags.add(USLT(encoding=1, lang="und", desc="", text=values.lyrics))
        if values.cover:
            tags.add(APIC(encoding=1, mime="image/jpeg", type=3, desc="", data=values.cover))
        tags.update_to_v23()
        tags.save(path, v2_version=3, v1=0)

    def save(self, source, destination, values, cancel, *, overwrite=False):
        """Write, verify, then atomically publish a copy beside the destination."""
        values.validate()
        if values.cover:
            # Normalize at the boundary even if the caller already prepared an image.
            from dataclasses import replace

            values = replace(values, cover=prepare_cover(values.cover))
        destination = Path(destination).absolute()
        if destination.suffix.lower() != ".mp3":
            raise AppError("Имя результата должно заканчиваться на .mp3.")
        if destination.is_symlink():
            raise AppError("Сохранение по символической ссылке не поддерживается.")
        if destination.exists() and not overwrite:
            raise AppError("Файл уже существует. Выберите другое имя или подтвердите замену.")
        check_space(destination.parent, Path(source).stat().st_size + 4 * 1024 * 1024)
        fd, name = tempfile.mkstemp(prefix=".mdow-save-", suffix=".mp3", dir=destination.parent)
        os.close(fd)
        temporary = Path(name)
        try:
            copy_stream(source, temporary, cancel)
            self.write(temporary, values)
            cancel.check()
            if temporary.stat().st_size > MAX_BYTES:
                raise AppError("Размер MP3 с тегами превысил 500 МБ.")
            MP3(temporary)  # Require valid MPEG audio, not just an ID3 header.
            if self.read(temporary) != values or ID3(temporary).version != (2, 3, 0):
                raise AppError("Проверка записанных тегов не пройдена. Исходный файл сохранён.")
            with temporary.open("rb+") as stream:
                os.fsync(stream.fileno())
            cancel.check()
            if overwrite:
                os.replace(temporary, destination)
            elif os.name == "nt":
                os.rename(temporary, destination)  # Windows refuses an existing destination.
            else:
                os.link(temporary, destination)  # Atomic no-clobber publication.
                temporary.unlink()
        finally:
            temporary.unlink(missing_ok=True)
        return destination
