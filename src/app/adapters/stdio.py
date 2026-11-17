"""Safe standard streams for the GUI executable and its piped worker."""

import os
import sys


def _worker_output():
    if os.name != "nt":
        return None

    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetStdHandle.argtypes = [wintypes.DWORD]
    kernel.GetStdHandle.restype = wintypes.HANDLE
    kernel.GetFileType.argtypes = [wintypes.HANDLE]
    kernel.GetFileType.restype = wintypes.DWORD
    handle = kernel.GetStdHandle(-11)  # STD_OUTPUT_HANDLE, inherited from Popen.
    if not handle or kernel.GetFileType(handle) != 3:  # FILE_TYPE_PIPE
        return None

    kernel.DuplicateHandle.argtypes = [
        wintypes.HANDLE,
        wintypes.HANDLE,
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.HANDLE),
        wintypes.DWORD,
        wintypes.BOOL,
        wintypes.DWORD,
    ]
    kernel.DuplicateHandle.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    duplicate = wintypes.HANDLE()
    current_process = wintypes.HANDLE(-1)
    if not kernel.DuplicateHandle(
        current_process, handle, current_process, ctypes.byref(duplicate), 0, False, 2
    ):  # DUPLICATE_SAME_ACCESS; leave the original inherited handle owned by Windows.
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        descriptor = msvcrt.open_osfhandle(duplicate.value, os.O_WRONLY | os.O_BINARY)
    except OSError:
        kernel.CloseHandle(duplicate)
        raise
    return os.fdopen(descriptor, "w", buffering=1, encoding="utf-8")


def configure_stdio(*, worker=False):
    # --windowed/pythonw have None streams. Never attach or allocate a console.
    if sys.stdout is None:
        sys.stdout = (_worker_output() if worker else None) or open(
            os.devnull, "w", encoding="utf-8"
        )
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    if sys.stdin is None:
        sys.stdin = open(os.devnull, encoding="utf-8")
