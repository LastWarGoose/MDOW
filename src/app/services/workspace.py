import os
import shutil
import tempfile
import time
import uuid
from pathlib import Path


def lock(stream):
    stream.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)


def root():
    location = Path(tempfile.gettempdir()) / "mdow-workspaces-v1"
    location.mkdir(exist_ok=True)
    return location


def cleanup_stale():
    """Delete only old, marked and unlocked MDOW workspaces, never active jobs."""
    for directory in root().iterdir():
        if directory.is_symlink() or not directory.is_dir():
            continue
        try:
            if uuid.UUID(directory.name).hex != directory.name:
                continue
            marker = directory / ".mdow-owner"
            if marker.is_symlink() or marker.read_bytes() != b"MDOW workspace v1\n":
                continue
            if time.time() - marker.stat().st_mtime < 86400:
                continue
            with (directory / ".lock").open("r+b") as stream:
                lock(stream)
            shutil.rmtree(directory)
        except (OSError, ValueError):
            continue


class Workspace:
    def __init__(self):
        self.path = root() / uuid.uuid4().hex
        self.path.mkdir()
        (self.path / ".mdow-owner").write_bytes(b"MDOW workspace v1\n")
        self._lock = (self.path / ".lock").open("w+b")
        self._lock.write(b"1")
        self._lock.flush()
        lock(self._lock)

    def close(self):
        self._lock.close()
        shutil.rmtree(self.path)
