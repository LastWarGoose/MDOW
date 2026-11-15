from PySide6.QtCore import QThread, Signal

from app.models.task import AppError, Cancellation, Cancelled


class Worker(QThread):
    progress = Signal(object, int)
    metadata = Signal(object)
    result = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, operation, parent=None):
        super().__init__(parent)
        self.operation = operation
        self.cancel_token = Cancellation()

    def run(self):
        try:
            result = self.operation(self.cancel_token, self.progress.emit, self.metadata.emit)
        except Cancelled:
            self.cancelled.emit()
        except AppError as exc:
            self.failed.emit(str(exc))
        except PermissionError:
            self.failed.emit(
                "Нет доступа к файлу. Закройте его в других программах и проверьте права."
            )
        except OSError:
            self.failed.emit(
                "Ошибка чтения или записи. Проверьте файл, свободное место и права доступа."
            )
        except Exception:
            self.failed.emit(
                "Не удалось обработать файл. Попробуйте другой файл или повторите операцию."
            )
        else:
            self.result.emit(result)
