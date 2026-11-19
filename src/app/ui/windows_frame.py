"""Restore the native window placement when switching caption styles at fractional DPI."""

import ctypes
from ctypes import wintypes


class WindowPlacement(ctypes.Structure):
    _fields_ = [
        ("length", wintypes.UINT),
        ("flags", wintypes.UINT),
        ("showCmd", wintypes.UINT),
        ("ptMinPosition", wintypes.POINT),
        ("ptMaxPosition", wintypes.POINT),
        ("rcNormalPosition", wintypes.RECT),
    ]

    @classmethod
    def capture(cls, window_id):
        placement = cls(length=ctypes.sizeof(cls))
        if ctypes.windll.user32.GetWindowPlacement(
            wintypes.HWND(window_id), ctypes.byref(placement)
        ):
            return placement
        return None

    def restore(self, window_id):
        ctypes.windll.user32.SetWindowPlacement(wintypes.HWND(window_id), ctypes.byref(self))
