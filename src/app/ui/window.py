from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QFont, QIcon, QImage, QKeySequence, QShortcut
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
)

from app.adapters.covers import crop_cover, load_cover_source
from app.models.task import AppError, Tags
from app.services.audio import AudioService
from app.services.validation import safe_filename, youtube_url
from app.ui.cover_import import CoverDropArea, clipboard_cover_source, mime_source
from app.ui.crop import CropDialog
from app.ui.design import IndustrialBackground, IndustrialPanel
from app.ui.style import STYLE
from app.ui.worker import Worker

_NO_RESULT = object()


def label(text, name=None):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    if name:
        widget.setObjectName(name)
    widget.setWordWrap(True)
    return widget


def button(text, action, primary=False):
    widget = QPushButton(text)
    widget.clicked.connect(action)
    if primary:
        widget.setObjectName("primary")
    return widget


class MainWindow(QMainWindow):
    def __init__(self, service=None, *, check_tools=True):
        super().__init__()
        self.service = service or AudioService()
        self.worker = None
        self._job_result = _NO_RESULT
        self._job_success = None
        self.cover_data = None
        self.dirty = False
        self.closing = False
        self.ready = False
        self.editor_available = False
        self._was_maximized = False
        self.status_message = ""
        self.setWindowTitle("MDOW")
        self.setWindowIcon(QIcon(str(Path(__file__).resolve().parents[1] / "assets" / "md.ico")))
        self.resize(1080, 820)
        self.setMinimumSize(900, 700)
        self.setStyleSheet(STYLE)
        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(0.65)
        self.player.setAudioOutput(self.audio_output)
        self.player.playbackStateChanged.connect(self.playback_changed)
        self.player.errorOccurred.connect(
            lambda *_: self.on_error("Не удалось воспроизвести аудио.")
        )
        self.build_ui()
        self.url.setFocus()
        self.paste_cover_shortcut = QShortcut(QKeySequence("Ctrl+Shift+V"), self)
        self.paste_cover_shortcut.activated.connect(self.paste_cover)
        self.fullscreen_shortcut = QShortcut(self)
        self.fullscreen_shortcut.setKeys([QKeySequence("Alt+Return"), QKeySequence("Alt+Enter")])
        self.fullscreen_shortcut.setAutoRepeat(False)
        self.fullscreen_shortcut.activated.connect(self.toggle_fullscreen)
        if check_tools:
            QTimer.singleShot(0, self.check_tools)

    def toggle_fullscreen(self):
        if self.isFullScreen():
            if self._was_maximized:
                self.showMaximized()
            else:
                self.showNormal()
        else:
            self._was_maximized = self.isMaximized()
            self.showFullScreen()

    def build_ui(self):
        central = IndustrialBackground()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(28, 20, 28, 22)
        layout.setSpacing(20)
        heading = QHBoxLayout()
        brand = label("MDOW", "brand")
        font = brand.font()
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 6)
        brand.setFont(font)
        heading.addWidget(brand)
        heading.addStretch()
        self.terms_button = button(
            "Условия YouTube ↗",
            lambda: QDesktopServices.openUrl(QUrl("https://www.youtube.com/static?template=terms")),
        )
        self.terms_button.setObjectName("terms")
        heading.addWidget(self.terms_button, alignment=Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(heading)

        source = IndustrialPanel()
        source_layout = QVBoxLayout(source)
        source_layout.setContentsMargins(20, 16, 20, 16)
        source_layout.setSpacing(14)
        source_layout.addWidget(label("Добавьте аудио", "heading"))
        row = QHBoxLayout()
        self.url = QLineEdit()
        self.url.setPlaceholderText("https://www.youtube.com/watch?v=…")
        self.url.setAccessibleName("Ссылка на ролик YouTube")
        self.url.returnPressed.connect(self.start_download)
        self.download_button = button("Загрузить аудио", self.start_download, True)
        self.import_button = button("Открыть файл…", self.import_file)
        row.addWidget(self.url, 1)
        row.addWidget(self.download_button)
        row.addWidget(self.import_button)
        source_layout.addLayout(row)
        layout.addWidget(source)

        self.editor = IndustrialPanel()
        edit_layout = QVBoxLayout(self.editor)
        edit_layout.setContentsMargins(20, 18, 20, 18)
        edit_layout.setSpacing(14)
        edit_layout.addWidget(label("Оформите дорожку", "heading"))
        columns = QHBoxLayout()
        columns.setSpacing(24)
        cover_column = QVBoxLayout()
        cover_column.setSpacing(10)
        self.cover = CoverDropArea()
        self.cover.dropped.connect(self.import_cover_mime)
        self.cover.chooseRequested.connect(self.choose_cover)
        self.cover.pasteRequested.connect(self.paste_cover)
        self.cover_button = button("Обложка…", self.choose_cover)
        self.cover_button.setToolTip(
            "Выберите изображение, затем выделите квадратный фрагмент обложки."
        )
        self.remove_cover_button = button("Убрать", self.remove_cover)
        self.remove_cover_button.setToolTip("Удалить обложку из тегов MP3")
        cover_column.addWidget(self.cover)
        cover_actions = QHBoxLayout()
        cover_actions.addWidget(self.cover_button)
        cover_actions.addWidget(self.remove_cover_button)
        cover_column.addLayout(cover_actions)
        self.play_button = button("▶  Прослушать", self.toggle_play)
        cover_column.addWidget(self.play_button)
        self.duration = label("Аудио ещё не добавлено", "muted")
        self.duration.setWordWrap(False)
        cover_column.addWidget(self.duration)
        cover_column.addStretch()
        columns.addLayout(cover_column)
        fields = QGridLayout()
        fields.setVerticalSpacing(10)
        fields.setColumnStretch(1, 1)
        self.title_input = QLineEdit()
        self.artist_input = QLineEdit()
        self.album_input = QLineEdit()
        for row, (text, widget) in enumerate(
            [
                ("Название", self.title_input),
                ("Исполнитель", self.artist_input),
                ("Альбом", self.album_input),
            ]
        ):
            widget.setMaxLength(10000)
            widget.setMinimumHeight(40)
            widget.setAccessibleName(text)
            widget.textEdited.connect(self.mark_dirty)
            field_label = label(text, "muted")
            field_label.setWordWrap(False)
            field_label.setBuddy(widget)
            fields.addWidget(field_label, row, 0)
            fields.addWidget(widget, row, 1)
        fields.addWidget(label("Текст песни", "muted"), 3, 0, 1, 2)
        self.lyrics = QPlainTextEdit()
        self.lyrics.setAccessibleName("Текст песни")
        self.lyrics.setPlaceholderText("Вставьте текст песни. Переносы строк сохранятся.")
        self.lyrics.setMinimumHeight(120)
        self.lyrics.textChanged.connect(self.mark_dirty)
        fields.addWidget(self.lyrics, 4, 0, 1, 2)
        fields.setRowStretch(4, 1)
        self.counter = label("0 / 100 000 символов", "muted")
        self.counter.setWordWrap(False)
        fields.addWidget(self.counter, 5, 0, 1, 2)
        columns.addLayout(fields, 1)
        edit_layout.addLayout(columns)
        self.editor.setMinimumHeight(470)
        editor_scroll = QScrollArea()
        editor_scroll.setFrameShape(QFrame.Shape.NoFrame)
        editor_scroll.setWidgetResizable(True)
        editor_scroll.setWidget(self.editor)
        layout.addWidget(editor_scroll, 1)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(4)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        footer = QHBoxLayout()
        footer.addStretch(1)
        self.cancel_button = button("Отменить", self.cancel)
        self.save_button = button("Сохранить MP3…", self.save_file, True)
        footer.addWidget(self.cancel_button)
        footer.addWidget(self.save_button)
        layout.addLayout(footer)
        self.update_controls()

    def mark_dirty(self, *_):
        self.dirty = True
        count = len(self.lyrics.toPlainText())
        self.counter.setText(f"{count:,} / 100 000 символов".replace(",", " "))
        self.update_controls()

    def update_controls(self):
        busy = self.worker is not None
        self.download_button.setEnabled(not busy)
        self.import_button.setEnabled(not busy)
        self.url.setEnabled(not busy)
        self.editor.setEnabled(self.editor_available)
        self.cover.setEnabled(self.editor_available and not busy)
        self.cover_button.setEnabled(self.editor_available and not busy)
        self.remove_cover_button.setEnabled(
            self.editor_available and not busy and bool(self.cover_data)
        )
        self.save_button.setEnabled(
            self.ready and not busy and len(self.lyrics.toPlainText()) <= 100000
        )
        self.play_button.setEnabled(self.ready and not busy)
        self.cancel_button.setEnabled(busy)

    def run_job(self, operation, success):
        if self.worker is not None:
            return
        self.worker = Worker(operation, self)
        self._job_result = _NO_RESULT
        self._job_success = success
        self.worker.progress.connect(self.on_progress)
        self.worker.metadata.connect(self.on_metadata)
        self.worker.result.connect(self.remember_result)
        self.worker.failed.connect(self.on_error)
        self.worker.cancelled.connect(lambda: self.set_status("Операция отменена"))
        self.worker.finished.connect(self.job_finished)
        self.update_controls()
        self.worker.start()

    def remember_result(self, result):
        self._job_result = result

    def job_finished(self):
        worker = self.worker
        self.worker = None
        result, success = self._job_result, self._job_success
        self._job_result, self._job_success = _NO_RESULT, None
        worker.deleteLater()
        self.progress.setRange(0, 100)
        if self.closing:
            self.close()
            return
        if result is not _NO_RESULT:
            success(result)
        self.update_controls()

    def set_status(self, message):
        self.status_message = message
        self.progress.setToolTip(message)
        self.progress.setAccessibleDescription(message)

    def on_error(self, message):
        self.set_status(message)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        dialog = QMessageBox(self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.setWindowTitle("MDOW")
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setText(message)
        dialog.setStandardButtons(QMessageBox.StandardButton.Ok)
        dialog.open()

    def on_progress(self, state, percent):
        self.set_status(str(state))
        self.progress.setRange(0, 0 if percent < 0 else 100)
        if percent >= 0:
            self.progress.setValue(percent)

    def on_metadata(self, values):
        self.title_input.setText(values.title)
        self.artist_input.setText(values.artist)
        self.album_input.setText(values.album)
        self.lyrics.setPlainText(values.lyrics)
        self.set_cover(values.cover)
        self.editor_available = True
        self.dirty = True
        self.update_controls()

    def check_tools(self):
        self.set_status("Проверка FFmpeg и ffprobe…")
        self.run_job(
            lambda cancel, *_: self.service.startup(cancel),
            lambda _: self.set_status("Готово к работе"),
        )

    def confirm_discard(self):
        if not self.dirty:
            return True
        return (
            QMessageBox.question(
                self,
                "Несохранённые изменения",
                "Изменения не сохранены. Продолжить без сохранения?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            == QMessageBox.StandardButton.Yes
        )

    def reset_editor(self):
        self.player.stop()
        self.player.setSource(QUrl())
        self.ready = False
        self.editor_available = False
        for widget in (self.title_input, self.artist_input, self.album_input):
            widget.clear()
        self.lyrics.clear()
        self.set_cover(None)
        self.dirty = False
        self.duration.setText("Подготовка аудио…")

    def prepare(self, source, is_url):
        if self.worker is not None or not self.confirm_discard():
            return
        self.reset_editor()
        self.run_job(
            lambda c, p, m: self.service.prepare(source, is_url, c, p, m), self.audio_ready
        )

    def start_download(self):
        if self.worker:
            return
        try:
            url = youtube_url(self.url.text())
        except AppError as exc:
            self.on_error(str(exc))
            return
        self.prepare(url, True)

    def import_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Открыть аудио",
            "",
            "Аудио (*.mp3 *.wav *.flac *.m4a *.ogg *.opus *.aac *.wma);;Все файлы (*)",
        )
        if path:
            self.prepare(path, False)

    def audio_ready(self, result):
        self.ready = True
        self.editor_available = True
        seconds = int(result["duration"])
        self.duration.setText(f"{seconds // 60}:{seconds % 60:02d}  ·  MP3")
        self.player.setSource(QUrl.fromLocalFile(str(result["path"])))
        self.set_status("Аудио готово. Отредактируйте теги и сохраните MP3.")
        self.progress.setRange(0, 100)
        self.progress.setValue(100)

    def set_cover(self, data):
        self.cover_data = data
        self.cover.set_image(data)

    def choose_cover(self):
        if self.worker or not self.editor_available:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Выбрать обложку", "", "Изображения (*.jpg *.jpeg *.png *.webp *.bmp *.gif)"
        )
        if path:
            self.import_cover_source(Path(path))

    def paste_cover(self):
        if self.worker or not self.editor_available:
            return
        self.import_cover_mime(QApplication.clipboard().mimeData())

    def import_cover_mime(self, mime):
        if self.worker or not self.editor_available:
            return
        try:
            source = mime_source(mime)
        except AppError as exc:
            self.on_error(str(exc))
            return
        self.import_cover_source(source)

    def import_cover_source(self, source):
        if self.worker or not self.editor_available:
            return
        self.set_status("Подготовка изображения…")
        operation = clipboard_cover_source if isinstance(source, QImage) else load_cover_source
        self.run_job(lambda c, *_: operation(source, c), self.select_cover_crop)

    def select_cover_crop(self, source):
        dialog = CropDialog(source, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selection = dialog.selection()
            self.set_status("Подготовка обложки…")
            self.run_job(lambda c, *_: crop_cover(source, selection, c), self.cover_ready)
        else:
            self.set_status("Обложка не изменена")
        dialog.deleteLater()

    def cover_ready(self, data):
        self.set_cover(data)
        self.mark_dirty()
        self.set_status("Обложка добавлена. Сохраните MP3, чтобы записать изменения.")

    def remove_cover(self):
        self.set_cover(None)
        self.mark_dirty()

    def save_file(self):
        values = Tags(
            self.title_input.text(),
            self.artist_input.text(),
            self.album_input.text(),
            self.lyrics.toPlainText(),
            self.cover_data,
        )
        try:
            values.validate()
        except AppError as exc:
            self.on_error(str(exc))
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить MP3",
            str(Path.home() / "Music" / safe_filename(values.title)),
            "MP3 (*.mp3)",
            options=QFileDialog.Option.DontConfirmOverwrite,
        )
        if not path:
            return
        destination = Path(path)
        if destination.suffix.lower() != ".mp3":
            destination = destination.with_name(destination.name + ".mp3")
        overwrite = destination.exists()
        if (
            overwrite
            and QMessageBox.question(
                self,
                "Заменить файл?",
                f"Файл «{destination.name}» уже существует. Заменить его?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        # The snapshot is immutable; changes made while saving remain dirty.
        self.run_job(
            lambda c, p, _: self.service.save(destination, values, c, p, overwrite=overwrite),
            lambda result: self.saved(result, values),
        )

    def saved(self, path, snapshot):
        current = Tags(
            self.title_input.text(),
            self.artist_input.text(),
            self.album_input.text(),
            self.lyrics.toPlainText(),
            self.cover_data,
        )
        self.dirty = current != snapshot
        self.set_status(
            f"Сохранено: {path}" + (" · Есть новые несохранённые изменения" if self.dirty else "")
        )

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def playback_changed(self, state):
        self.play_button.setText(
            "Ⅱ  Пауза" if state == QMediaPlayer.PlaybackState.PlayingState else "▶  Прослушать"
        )

    def cancel(self):
        if self.worker:
            self.worker.cancel_token.cancel()
            self.set_status("Отмена операции…")
            self.cancel_button.setEnabled(False)

    def closeEvent(self, event):
        if self.worker:
            if (
                not self.closing
                and QMessageBox.question(
                    self, "Закрыть MDOW?", "Остановить текущую операцию и закрыть приложение?"
                )
                != QMessageBox.StandardButton.Yes
            ):
                event.ignore()
                return
            self.closing = True
            self.cancel()
            event.ignore()
            return
        if not self.closing and not self.confirm_discard():
            event.ignore()
            return
        self.player.stop()
        self.player.setSource(QUrl())
        try:
            self.service.close()
        except OSError:
            pass  # A locked workspace is retried by the stale cleanup on next start.
        event.accept()
