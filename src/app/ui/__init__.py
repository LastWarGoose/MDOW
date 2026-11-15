"""Qt UI configuration, applied before loading the multimedia backend."""

import os

# Decoder diagnostics can include embedded titles, lyrics and local paths.
os.environ["QT_FFMPEG_DEBUG"] = "0"
os.environ["QT_LOGGING_RULES"] = os.environ.get("QT_LOGGING_RULES", "") + "\nqt.multimedia.*=false"
os.environ["QT_FFMPEG_PROTOCOL_WHITELIST"] = "file,pipe"
