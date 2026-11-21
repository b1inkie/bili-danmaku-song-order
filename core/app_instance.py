"""One packaged GUI per portable directory; avoids an updater replacing another instance."""
import ctypes
from ctypes import wintypes
import hashlib
from pathlib import Path
import sys

_handle = None


def acquire():
    global _handle
    if sys.platform != 'win32' or not getattr(sys, 'frozen', False):
        return True
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    key = hashlib.sha256(str(Path(sys.executable).resolve()).lower().encode()).hexdigest()
    _handle = kernel.CreateMutexW(None, False, 'Local\\BiliSongdesk-' + key)
    if not _handle:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == 183:
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle(_handle)
        _handle = None
        return False
    return True
