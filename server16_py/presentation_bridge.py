"""Read-only acknowledgements from FIFA's native scene loaders."""
from __future__ import annotations
import ctypes as C
import struct
import time

SIZE = 72
NAMES = ('entrance_props', 'stadium_pyrotechnics', 'var_cabin', 'smoke_machine')


def decode_status(raw, pid, now):
    if len(raw) != SIZE:
        return {}
    words = struct.unpack('<18I', raw)
    if words[:2] != (1, pid):
        return {}
    result = {}
    for i, name in enumerate(NAMES):
        sequence, state, heartbeat, generation = words[2+i*4:6+i*4]
        # Before the first SLE scene callback, a registered loader legitimately
        # retains Waiting with no new heartbeat. Do not call that a missing DLL.
        fresh = ((now-heartbeat) & 0xffffffff) <= 5000
        if sequence and not sequence & 1 and 1 <= state <= 5 and (fresh or state == 1):
            result[name] = state
    return result


class PresentationBridge:
    def __init__(self):
        self.pid = 0
        self.pointer = self.handle = None
        self.next_open = 0.0
        self.kernel = C.WinDLL('kernel32', use_last_error=True)
        self.kernel.OpenFileMappingW.argtypes = [C.c_uint32, C.c_int, C.c_wchar_p]
        self.kernel.OpenFileMappingW.restype = C.c_void_p
        self.kernel.MapViewOfFile.argtypes = [C.c_void_p, C.c_uint32, C.c_uint32, C.c_uint32, C.c_size_t]
        self.kernel.MapViewOfFile.restype = C.c_void_p
        self.kernel.UnmapViewOfFile.argtypes = [C.c_void_p]
        self.kernel.CloseHandle.argtypes = [C.c_void_p]
        self.kernel.GetTickCount.restype = C.c_uint32

    def read(self, pid):
        if pid != self.pid:
            self.close()
            self.pid = pid
        if not pid:
            return {}
        if not self.pointer and time.monotonic() >= self.next_open:
            self.next_open = time.monotonic()+1
            # Open only: never create an empty channel or write to FIFA.
            self.handle = self.kernel.OpenFileMappingW(4, False, f'Local\\FIFA16_PresentationLoad_v1_{pid}')
            if self.handle:
                self.pointer = self.kernel.MapViewOfFile(self.handle, 4, 0, 0, SIZE)
                if not self.pointer:
                    self.kernel.CloseHandle(self.handle)
                    self.handle = None
        if not self.pointer:
            return {}
        raw = C.string_at(self.pointer, SIZE)
        result = decode_status(raw, pid, self.kernel.GetTickCount())
        for i, name in enumerate(NAMES):
            if C.string_at(self.pointer+8+i*16, 4) != raw[8+i*16:12+i*16]:
                result.pop(name, None)
        return result

    def close(self):
        if self.pointer:
            self.kernel.UnmapViewOfFile(self.pointer)
        if self.handle:
            self.kernel.CloseHandle(self.handle)
        self.pointer = self.handle = None
        self.next_open = 0.0

