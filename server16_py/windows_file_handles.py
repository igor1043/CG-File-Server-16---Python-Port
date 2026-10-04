"""Safe, out-of-process Windows file-handle inspection.

This module never patches or executes code inside the target process.  It uses
the system handle table, duplicates only the target's handles into Server16,
and asks Windows for paths only when ``GetFileType`` identifies a disk file.
"""
from __future__ import annotations

import ctypes
import os
from pathlib import Path
from typing import Iterable


if os.name == "nt":
    from ctypes import wintypes

    _STATUS_INFO_LENGTH_MISMATCH = 0xC0000004
    _SYSTEM_EXTENDED_HANDLE_INFORMATION = 64
    _PROCESS_DUP_HANDLE = 0x0040
    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    _DUPLICATE_SAME_ACCESS = 0x00000002
    _FILE_TYPE_DISK = 0x0001

    class _SystemHandleEntryEx(ctypes.Structure):
        _fields_ = [
            ("object", ctypes.c_void_p),
            ("process_id", ctypes.c_size_t),
            ("handle_value", ctypes.c_size_t),
            ("granted_access", wintypes.ULONG),
            ("creator_backtrace_index", wintypes.USHORT),
            ("object_type_index", wintypes.USHORT),
            ("handle_attributes", wintypes.ULONG),
            ("reserved", wintypes.ULONG),
        ]

    _ntdll = ctypes.WinDLL("ntdll", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _ntdll.NtQuerySystemInformation.argtypes = [
        wintypes.ULONG,
        ctypes.c_void_p,
        wintypes.ULONG,
        ctypes.POINTER(wintypes.ULONG),
    ]
    _ntdll.NtQuerySystemInformation.restype = ctypes.c_long
    _kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.GetCurrentProcess.argtypes = []
    _kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    _kernel32.DuplicateHandle.argtypes = [
        wintypes.HANDLE,
        wintypes.HANDLE,
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.HANDLE),
        wintypes.DWORD,
        wintypes.BOOL,
        wintypes.DWORD,
    ]
    _kernel32.DuplicateHandle.restype = wintypes.BOOL
    _kernel32.GetFileType.argtypes = [wintypes.HANDLE]
    _kernel32.GetFileType.restype = wintypes.DWORD
    _kernel32.GetFinalPathNameByHandleW.argtypes = [
        wintypes.HANDLE,
        wintypes.LPWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
    ]
    _kernel32.GetFinalPathNameByHandleW.restype = wintypes.DWORD
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL


def normalized_disk_path(value: str | Path) -> str:
    raw = str(value).strip()
    if raw.startswith("\\\\?\\UNC\\"):
        raw = "\\\\" + raw[8:]
    elif raw.startswith("\\\\?\\"):
        raw = raw[4:]
    return os.path.normcase(os.path.abspath(os.path.normpath(raw)))


def _system_handles_buffer() -> tuple[ctypes.Array, int]:
    size = 1 << 20
    while size <= (1 << 28):
        buffer = ctypes.create_string_buffer(size)
        required = wintypes.ULONG(0)
        status = int(
            _ntdll.NtQuerySystemInformation(
                _SYSTEM_EXTENDED_HANDLE_INFORMATION,
                buffer,
                size,
                ctypes.byref(required),
            )
        ) & 0xFFFFFFFF
        if status == 0:
            count = int(ctypes.c_size_t.from_buffer(buffer, 0).value)
            return buffer, count
        if status != _STATUS_INFO_LENGTH_MISMATCH:
            raise OSError(f"NtQuerySystemInformation failed: 0x{status:08X}")
        size = max(size * 2, int(required.value) + 65536)
    raise OSError("Windows handle table exceeded the safe inspection limit")


def find_exact_open_disk_path(
    process_id: int,
    candidates: Iterable[str | Path],
) -> str | None:
    """Return a candidate currently open as a disk file by ``process_id``.

    The returned value is the caller's canonical candidate, not an unchecked
    path obtained from the target process.
    """
    if os.name != "nt" or int(process_id) <= 0:
        return None
    expected = {normalized_disk_path(item): str(Path(item).resolve()) for item in candidates}
    if not expected:
        return None

    process = _kernel32.OpenProcess(
        _PROCESS_DUP_HANDLE | _PROCESS_QUERY_LIMITED_INFORMATION,
        False,
        int(process_id),
    )
    if not process:
        raise PermissionError(ctypes.get_last_error(), "OpenProcess failed")
    try:
        buffer, count = _system_handles_buffer()
        offset = ctypes.sizeof(ctypes.c_size_t) * 2
        entry_size = ctypes.sizeof(_SystemHandleEntryEx)
        current_process = _kernel32.GetCurrentProcess()
        for index in range(count):
            entry_offset = offset + index * entry_size
            if entry_offset + entry_size > len(buffer):
                break
            entry = _SystemHandleEntryEx.from_buffer(buffer, entry_offset)
            if int(entry.process_id) != int(process_id):
                continue
            duplicate = wintypes.HANDLE()
            if not _kernel32.DuplicateHandle(
                process,
                wintypes.HANDLE(int(entry.handle_value)),
                current_process,
                ctypes.byref(duplicate),
                0,
                False,
                _DUPLICATE_SAME_ACCESS,
            ):
                continue
            try:
                if _kernel32.GetFileType(duplicate) != _FILE_TYPE_DISK:
                    continue
                path_buffer = ctypes.create_unicode_buffer(32768)
                length = _kernel32.GetFinalPathNameByHandleW(
                    duplicate, path_buffer, len(path_buffer), 0
                )
                if not length or length >= len(path_buffer):
                    continue
                match = expected.get(normalized_disk_path(path_buffer.value))
                if match:
                    return match
            finally:
                _kernel32.CloseHandle(duplicate)
    finally:
        _kernel32.CloseHandle(process)
    return None


__all__ = ["find_exact_open_disk_path", "normalized_disk_path"]
