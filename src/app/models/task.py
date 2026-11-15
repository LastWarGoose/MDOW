from dataclasses import dataclass
from enum import StrEnum
from threading import Event


class AppError(Exception):
    """An error safe to display to the user."""


class Cancelled(AppError):
    pass


class Cancellation:
    def __init__(self):
        self._event = Event()

    def cancel(self):
        self._event.set()

    def check(self):
        if self._event.is_set():
            raise Cancelled("Операция отменена.")

    def wait(self, seconds):
        if self._event.wait(seconds):
            self.check()


class State(StrEnum):
    IDLE = "Готов к работе"
    CHECKING = "Проверка"
    DOWNLOADING = "Загрузка"
    CONVERTING = "Конвертация"
    EDITING = "Редактирование"
    SAVING = "Сохранение"
    COMPLETED = "Завершено"
    ERROR = "Ошибка"
    CANCELLED = "Отменено"


class TaskState:
    def __init__(self):
        self.current = State.IDLE

    def move(self, target):
        allowed = {
            State.IDLE: {State.CHECKING},
            State.CHECKING: {State.DOWNLOADING, State.CONVERTING, State.EDITING},
            State.DOWNLOADING: {State.CONVERTING},
            State.CONVERTING: {State.EDITING},
            State.EDITING: {State.SAVING, State.CHECKING},
            State.SAVING: {State.COMPLETED},
            State.COMPLETED: {State.SAVING, State.CHECKING},
            State.ERROR: {State.CHECKING, State.SAVING},
            State.CANCELLED: {State.CHECKING, State.SAVING},
        }
        if target not in allowed[self.current] | {State.ERROR, State.CANCELLED}:
            raise AppError("Недопустимый переход состояния задачи.")
        self.current = target


@dataclass(frozen=True)
class Tags:
    title: str = ""
    artist: str = ""
    album: str = ""
    lyrics: str = ""
    cover: bytes | None = None

    def validate(self):
        if len(self.lyrics) > 100_000:
            raise AppError("Текст песни должен быть не длиннее 100 000 символов.")
        if any(len(v) > 10_000 for v in (self.title, self.artist, self.album)):
            raise AppError("Поле тега должно быть не длиннее 10 000 символов.")
        if any("\x00" in v for v in (self.title, self.artist, self.album, self.lyrics)):
            raise AppError("Теги не должны содержать нулевые символы.")
