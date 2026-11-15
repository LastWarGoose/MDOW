# Компоненты и лицензии

MDOW использует сторонние компоненты. Этот документ не заменяет оригинальные тексты
лицензий и их обязательства при распространении.

| Компонент | Лицензия / официальный источник |
| --- | --- |
| PySide6 / Qt | LGPLv3, GPL или коммерческая, в зависимости от компонента: https://doc.qt.io/qtforpython-6/licenses.html |
| yt-dlp | Unlicense; дополнительные зависимости имеют свои лицензии: https://github.com/yt-dlp/yt-dlp/blob/master/LICENSE |
| yt-dlp-ejs | Unlicense AND MIT AND ISC (метаданные пакета 0.8.0): https://github.com/yt-dlp/ejs |
| Mutagen | GPL-2.0-or-later: https://github.com/quodlibet/mutagen/blob/master/COPYING |
| Pillow | HPND и лицензии включённых кодеков: https://github.com/python-pillow/Pillow/blob/main/LICENSE |
| FFmpeg | LGPL/GPL в зависимости от конфигурации: https://ffmpeg.org/legal.html |
| Deno | MIT и уведомления встроенных компонентов: https://github.com/denoland/deno/blob/main/LICENSE.md |
| PyInstaller | GPL с исключением для распространения сборок: https://pyinstaller.org/en/stable/license.html |

FFmpeg Gyan Essentials используется как отдельный исполняемый инструмент.
У этой сборки включён GPL; проверяйте `ffmpeg -L` и `ffmpeg -buildconf`. Её исходники
и уведомления: https://github.com/GyanD/codexffmpeg/releases/tag/8.0.1.
Обычная сборка MDOW не добавляет FFmpeg или Deno автоматически. Режим `--onefile`
для локального использования включает установленные инструменты и их лицензии в EXE.
Это относится к командным инструментам: Qt Multimedia включает собственные библиотеки
декодирования FFmpeg, для которых также нужны соответствующие лицензионные уведомления.

При сборке тексты лицензий установленных Python-дистрибутивов копируются в
`dist/MDOW/third-party-licenses/`. Перед распространением проверьте полноту,
совместимость выбранной лицензии MDOW с Mutagen и Qt, а также доступность
соответствующих исходников и возможности замены библиотек там, где это требуется.
