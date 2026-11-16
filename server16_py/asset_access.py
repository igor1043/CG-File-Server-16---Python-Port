"""Restore a managed asset's normal inheritance using the current token only.

No ownership changes, privilege enabling, broad grants, subprocesses or UAC.
Explicit access rules are retained; Windows remains the final authority.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from functools import lru_cache
import os
from pathlib import Path

DACL_SECURITY_INFORMATION = 0x00000004
UNPROTECTED_DACL_SECURITY_INFORMATION = 0x20000000
SE_DACL_PROTECTED = 0x1000
SE_FILE_OBJECT = 1


@lru_cache(maxsize=1)
def _api():
    advapi = ctypes.WinDLL('advapi32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    pointer = ctypes.c_void_p
    advapi.GetNamedSecurityInfoW.argtypes = [wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD,
        pointer, pointer, ctypes.POINTER(pointer), pointer, ctypes.POINTER(pointer)]
    advapi.GetNamedSecurityInfoW.restype = wintypes.DWORD
    advapi.GetSecurityDescriptorControl.argtypes = [pointer, ctypes.POINTER(wintypes.WORD),
        ctypes.POINTER(wintypes.DWORD)]
    advapi.GetSecurityDescriptorControl.restype = wintypes.BOOL
    advapi.SetNamedSecurityInfoW.argtypes = [wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD,
        pointer, pointer, pointer, pointer]
    advapi.SetNamedSecurityInfoW.restype = wintypes.DWORD
    kernel.LocalFree.argtypes = [pointer]
    kernel.LocalFree.restype = pointer
    return advapi, kernel


def restore_asset_inheritance(path: str | Path, log=None, *, refresh: bool = False) -> bool:
    """Unprotect one existing asset's DACL when the current user may do so.

    Retain its owner and explicit ACEs, then let Windows apply the parent's
    inheritance. Never pass a NULL DACL (which would grant everyone access).
    A protected installation whose ACL the user cannot edit returns False.
    """
    if os.name != 'nt':
        return False
    path = Path(path).absolute()
    descriptor, dacl = ctypes.c_void_p(), ctypes.c_void_p()
    kernel = None
    try:
        # Do not repair an unrelated directory through a link or mount point.
        for current in (path, *path.parents):
            if current.lstat().st_file_attributes & 0x400:
                return False
        advapi, kernel = _api()
        error = advapi.GetNamedSecurityInfoW(str(path), SE_FILE_OBJECT, DACL_SECURITY_INFORMATION,
            None, None, ctypes.byref(dacl), None, ctypes.byref(descriptor))
        if error:
            raise ctypes.WinError(error)
        control, revision = wintypes.WORD(), wintypes.DWORD()
        if not advapi.GetSecurityDescriptorControl(descriptor, ctypes.byref(control), ctypes.byref(revision)):
            raise ctypes.WinError(ctypes.get_last_error())
        protected = bool(control.value & SE_DACL_PROTECTED)
        if (not protected and not refresh) or not dacl.value:
            return False
        error = advapi.SetNamedSecurityInfoW(str(path), SE_FILE_OBJECT,
            DACL_SECURITY_INFORMATION | UNPROTECTED_DACL_SECURITY_INFORMATION,
            None, None, dacl, None)
        if error:
            raise ctypes.WinError(error)
        if protected and callable(log):
            log(f'Asset permission inheritance restored without elevation: {path}')
        return True
    except OSError as exc:
        if callable(log):
            log(f'Current user cannot restore asset inheritance: {path}', exc)
        return False
    finally:
        if descriptor.value and kernel is not None:
            kernel.LocalFree(descriptor)
