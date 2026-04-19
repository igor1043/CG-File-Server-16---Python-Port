from __future__ import annotations

import ctypes
import struct
from ctypes import wintypes
from pathlib import Path


PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
PROCESS_VM_OPERATION = 0x0008
PROCESS_QUERY_INFORMATION = 0x0400
PAGE_READWRITE = 0x04
TH32CS_SNAPMODULE = 0x00000008
TH32CS_SNAPMODULE32 = 0x00000010
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
MAX_MODULE_NAME32 = 255
MAX_PATH = 260


class MODULEENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("th32ModuleID", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("GlblcntUsage", wintypes.DWORD),
        ("ProccntUsage", wintypes.DWORD),
        ("modBaseAddr", ctypes.POINTER(ctypes.c_ubyte)),
        ("modBaseSize", wintypes.DWORD),
        ("hModule", wintypes.HMODULE),
        ("szModule", wintypes.WCHAR * (MAX_MODULE_NAME32 + 1)),
        ("szExePath", wintypes.WCHAR * MAX_PATH),
    ]


class MemoryAccessError(RuntimeError):
    pass


class Memory:
    def __init__(self) -> None:
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel32.OpenProcess.restype = wintypes.HANDLE
        self.kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel32.ReadProcessMemory.restype = wintypes.BOOL
        self.kernel32.ReadProcessMemory.argtypes = [
            wintypes.HANDLE,
            wintypes.LPCVOID,
            wintypes.LPVOID,
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        self.kernel32.WriteProcessMemory.restype = wintypes.BOOL
        self.kernel32.WriteProcessMemory.argtypes = [
            wintypes.HANDLE,
            wintypes.LPVOID,
            wintypes.LPCVOID,
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        self.kernel32.VirtualProtectEx.restype = wintypes.BOOL
        self.kernel32.VirtualProtectEx.argtypes = [
            wintypes.HANDLE,
            wintypes.LPVOID,
            ctypes.c_size_t,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        self.kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        self.kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        self.kernel32.Module32FirstW.restype = wintypes.BOOL
        self.kernel32.Module32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MODULEENTRY32W)]
        self.kernel32.Module32NextW.restype = wintypes.BOOL
        self.kernel32.Module32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MODULEENTRY32W)]
        self.kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self.process_handle = None
        self.process_name = ""
        self.process_id = 0
        self.base_module = 0

    def close(self) -> None:
        if self.process_handle:
            self.kernel32.CloseHandle(self.process_handle)
            self.process_handle = None

    def __del__(self) -> None:
        self.close()

    def attack(self, process_name: str) -> bool:
        import psutil

        self.close()
        for proc in psutil.process_iter(["pid", "name", "exe"]):
            name = (proc.info.get("name") or "").lower()
            if Path(name).stem == process_name.lower():
                self.process_id = proc.info["pid"]
                self.process_name = process_name
                rights = PROCESS_QUERY_INFORMATION | PROCESS_VM_READ | PROCESS_VM_WRITE | PROCESS_VM_OPERATION
                self.process_handle = self.kernel32.OpenProcess(rights, False, self.process_id)
                if not self.process_handle:
                    return False
                self.base_module = self._get_base_address(proc.info.get("exe"))
                return True
        return False

    def _get_base_address(self, exe_path: str | None) -> int:
        snapshot = self.kernel32.CreateToolhelp32Snapshot(
            TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32,
            self.process_id,
        )
        if snapshot == INVALID_HANDLE_VALUE:
            return 0
        try:
            entry = MODULEENTRY32W()
            entry.dwSize = ctypes.sizeof(MODULEENTRY32W)
            ok = self.kernel32.Module32FirstW(snapshot, ctypes.byref(entry))
            target_name = Path(exe_path).name.lower() if exe_path else ""
            while ok:
                module_name = entry.szModule.lower()
                module_path = entry.szExePath.lower()
                if not target_name or module_name == target_name or Path(module_path).name.lower() == target_name:
                    return ctypes.addressof(entry.modBaseAddr.contents)
                ok = self.kernel32.Module32NextW(snapshot, ctypes.byref(entry))
        finally:
            self.kernel32.CloseHandle(snapshot)
        return 0

    def is_open(self) -> bool:
        return bool(self.process_handle)

    def read_process_memory(self, address: int, size: int) -> bytes:
        if not self.process_handle:
            raise MemoryAccessError("Process handle not open")
        buffer = ctypes.create_string_buffer(size)
        read = ctypes.c_size_t()
        ok = self.kernel32.ReadProcessMemory(
            self.process_handle,
            ctypes.c_void_p(address),
            buffer,
            size,
            ctypes.byref(read),
        )
        if not ok:
            raise MemoryAccessError(f"ReadProcessMemory failed at 0x{address:X}")
        return buffer.raw[: read.value]

    def write_process_memory(self, address: int, payload: bytes) -> None:
        if not self.process_handle:
            raise MemoryAccessError("Process handle not open")
        old = wintypes.DWORD()
        self.kernel32.VirtualProtectEx(
            self.process_handle,
            ctypes.c_void_p(address),
            len(payload),
            PAGE_READWRITE,
            ctypes.byref(old),
        )
        written = ctypes.c_size_t()
        ok = self.kernel32.WriteProcessMemory(
            self.process_handle,
            ctypes.c_void_p(address),
            payload,
            len(payload),
            ctypes.byref(written),
        )
        if not ok:
            raise MemoryAccessError(f"WriteProcessMemory failed at 0x{address:X}")

    def read_uint32(self, address: int) -> int:
        return struct.unpack("<I", self.read_process_memory(address, 4))[0]

    def read_int64(self, address: int) -> int:
        return struct.unpack("<q", self.read_process_memory(address, 8))[0]

    def read_string(self, address: int, size: int) -> str:
        raw = self.read_process_memory(address, size)
        return raw.split(b"\x00", 1)[0].decode("utf-8", errors="ignore")

    def resolve_pointer(self, static_ptr: int, offsets: list[int]) -> int:
        pointer = self.read_int64(self.base_module + static_ptr)
        if pointer == 0:
            raise MemoryAccessError(
                f"Null pointer at base chain start 0x{self.base_module + static_ptr:X}"
            )
        for offset in offsets[:-1]:
            address = pointer + offset
            pointer = self.read_int64(address)
            if pointer == 0:
                raise MemoryAccessError(f"Null pointer while resolving chain at 0x{address:X}")
        return pointer + offsets[-1]

    def trace_pointer_chain(self, static_ptr: int, offsets: list[int]) -> list[str]:
        trace: list[str] = []
        base_address = self.base_module + static_ptr
        trace.append(f"base_module=0x{self.base_module:X}")
        trace.append(f"static_ptr=0x{static_ptr:X}")
        trace.append(f"read [0x{base_address:X}]")
        pointer = self.read_int64(base_address)
        trace.append(f" -> 0x{pointer:X}")
        if pointer == 0:
            return trace
        for index, offset in enumerate(offsets[:-1]):
            address = pointer + offset
            trace.append(f"step {index}: read [0x{address:X}] (offset=0x{offset:X})")
            pointer = self.read_int64(address)
            trace.append(f" -> 0x{pointer:X}")
            if pointer == 0:
                return trace
        trace.append(f"final address=0x{pointer + offsets[-1]:X} (last offset=0x{offsets[-1]:X})")
        return trace

    def get_int(self, static_ptr: int, offsets: list[int]) -> int:
        return self.read_uint32(self.resolve_pointer(static_ptr, offsets))

    def get_string(self, static_ptr: int, offsets: list[int], size: int = 64) -> str:
        return self.read_string(self.resolve_pointer(static_ptr, offsets), size)

    def write_int(self, static_ptr: int, offsets: list[int], value: str | int) -> None:
        address = self.resolve_pointer(static_ptr, offsets)
        self.write_process_memory(address, struct.pack("<I", int(value)))

    def write_string_with_offsets(self, static_ptr: int, offsets: list[int], value: str) -> None:
        address = self.resolve_pointer(static_ptr, offsets)
        self.write_process_memory(address, value.encode("utf-8") + b"\x00")
