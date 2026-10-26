"""
d3d_injector.py
───────────────
Connects to the D3D overlay plugin already loaded by FIFA and the shared-memory
channel used to control what the overlay displays.

Usage (from app.py):
    injector = D3DOverlayInjector(dll_path="runtime/cgfs16_overlay.dll")
    injector.inject(fifa_pid)       # compatibility name; attach only, never inject
    injector.show("Bernabéu", "Copying files...", 0.0)
    injector.update(42.0, "Copying files...")
    injector.hide()
    injector.destroy()              # call on app exit
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import logging
import os
import threading
import hashlib
from pathlib import Path

log = logging.getLogger(__name__)


def _loaded_overlay_path(pid):
    """Read the module inventory; a Server restart must not add a second hook."""
    from .memory_access import Memory, MODULEENTRY32W, INVALID_HANDLE_VALUE
    probe = Memory()
    kernel = probe.kernel32
    snapshot = kernel.CreateToolhelp32Snapshot(24, pid)
    if not snapshot or snapshot == INVALID_HANDLE_VALUE:
        raise OSError('Não foi possível verificar os módulos do FIFA.')
    try:
        entry = MODULEENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        ok = kernel.Module32FirstW(snapshot, ctypes.byref(entry))
        if not ok:
            raise OSError('Não foi possível ler os módulos do FIFA.')
        matches = []
        while ok:
            if entry.szModule.casefold() == 'cgfs16_overlay.dll':
                matches.append(Path(entry.szExePath))
            ok = kernel.Module32NextW(snapshot, ctypes.byref(entry))
        if len(matches)>1:
            raise RuntimeError('Mais de uma overlay está carregada. Reinicie o FIFA.')
        return matches[0] if matches else None
    finally:
        kernel.CloseHandle(snapshot)

# ─────────────────────────────────────────────────────────────────────────────
# Shared memory layout — MUST match OverlayShared in cgfs16_overlay.cpp
# ─────────────────────────────────────────────────────────────────────────────
_SHMEM_NAME = "Local\\CGFS16_Overlay_v3"
_MAX_STR    = 256
_MAX_IMG    = 512


class _OverlayShared(ctypes.Structure):
    _fields_ = [
        ("visible",       ctypes.c_long),           # 0 = hide, 1 = show
        ("progress_x100", ctypes.c_long),           # progress * 100  (0–10000)
        ("stadium_name",  ctypes.c_wchar * _MAX_STR),
        ("detail_text",   ctypes.c_wchar * _MAX_STR),
        ("image_path",    ctypes.c_wchar * _MAX_IMG),  # abs path to preview image
        ("scoreboard_visible", ctypes.c_long),
        ("scoreboard_progress_x100", ctypes.c_long),
        ("scoreboard_name", ctypes.c_wchar * _MAX_STR),
        ("scoreboard_detail", ctypes.c_wchar * _MAX_STR),
        ("movie_visible", ctypes.c_long),
        ("movie_progress_x100", ctypes.c_long),
        ("movie_name", ctypes.c_wchar * _MAX_STR),
        ("movie_detail", ctypes.c_wchar * _MAX_STR),
        ("narration_visible", ctypes.c_long),
        ("narration_progress_x100", ctypes.c_long),
        ("narration_name", ctypes.c_wchar * _MAX_STR),
        ("narration_detail", ctypes.c_wchar * _MAX_STR),
        ("narration_image_path", ctypes.c_wchar * _MAX_IMG),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Win32 constants & kernel32 setup
# ─────────────────────────────────────────────────────────────────────────────
_PROCESS_CREATE_THREAD    = 0x0002
_PROCESS_VM_OPERATION     = 0x0008
_PROCESS_VM_WRITE         = 0x0020
_PROCESS_VM_READ          = 0x0010
_PROCESS_QUERY_INFORMATION = 0x0400
_MEM_COMMIT               = 0x1000
_MEM_RESERVE              = 0x2000
_MEM_RELEASE              = 0x8000
_PAGE_READWRITE           = 0x04
_FILE_MAP_ALL_ACCESS      = 0xF001F
_INVALID_HANDLE_VALUE     = ctypes.c_void_p(-1).value


def _configure_kernel32() -> ctypes.WinDLL:
    k = ctypes.WinDLL("kernel32", use_last_error=True)

    HANDLE  = wintypes.HANDLE
    BOOL    = wintypes.BOOL
    DWORD   = wintypes.DWORD
    LPCWSTR = wintypes.LPCWSTR
    LPVOID  = ctypes.c_void_p
    SIZE_T  = ctypes.c_size_t

    k.CloseHandle.argtypes = [HANDLE]
    k.CloseHandle.restype = BOOL

    k.CreateFileMappingW.argtypes = [
        HANDLE, LPVOID, DWORD, DWORD, DWORD, LPCWSTR]
    k.CreateFileMappingW.restype  = HANDLE

    k.MapViewOfFile.argtypes = [HANDLE, DWORD, DWORD, DWORD, SIZE_T]
    k.MapViewOfFile.restype  = LPVOID

    k.UnmapViewOfFile.argtypes = [LPVOID]
    k.UnmapViewOfFile.restype  = BOOL

    return k


_k32 = _configure_kernel32()


# ─────────────────────────────────────────────────────────────────────────────
# D3DOverlayInjector
# ─────────────────────────────────────────────────────────────────────────────
class D3DOverlayInjector:
    """Controls the installed overlay plugin through shared memory.

    The game-owned mod host loads the DLL at startup. Server16 only verifies
    its module inventory; it never starts a loader in another process.
    """

    def __init__(self, dll_path: str | Path) -> None:
        self._dll_path     = str(Path(dll_path).resolve())
        self._hmap: int    = 0
        self._shared_ptr   = 0          # raw address returned by MapViewOfFile
        self._shared: _OverlayShared | None = None
        self._injected_pid = 0
        self._lock         = threading.Lock()
        self._ready        = False

        self._open_shared_memory()

    # ── Public ────────────────────────────────────────────────────────────────

    def is_ready(self) -> bool:
        """True if the shared channel and the expected plugin build are available."""
        return self._ready and os.path.isfile(self._dll_path)

    def is_injected(self, pid: int = 0) -> bool:
        if pid:
            return self._injected_pid == pid
        return self._injected_pid != 0

    def inject(self, pid: int) -> bool:
        """Attach to an existing plugin. Never load code into an external PID."""
        if not self._ready:
            log.error("D3DOverlay: shared memory not ready")
            return False
        if not os.path.isfile(self._dll_path):
            log.error("D3DOverlay: DLL not found: %s", self._dll_path)
            return False
        with self._lock:
            if self._injected_pid == pid:
                return True
            try:
                loaded = _loaded_overlay_path(pid)
                if loaded is not None:
                    expected = hashlib.sha256(Path(self._dll_path).read_bytes()).digest()
                    if hashlib.sha256(loaded.read_bytes()).digest() != expected:
                        log.error('D3DOverlay: another version is loaded; FIFA restart required')
                        return False
                    self._injected_pid = pid
                    log.info('D3DOverlay: reusing the existing native overlay in pid=%d', pid)
                    return True
            except (OSError, RuntimeError) as exc:
                log.error('D3DOverlay: existing-module check failed: %s', exc)
                return False
            log.info('D3DOverlay: plugin not loaded in pid=%d; install the native mod and restart FIFA', pid)
            return False

    def show(self, stadium_name: str, detail: str = "", progress: float = 0.0,
             image_path: str = "") -> None:
        if not self._ready or self._shared is None:
            return
        self._shared.stadium_name  = stadium_name[:_MAX_STR - 1]
        self._shared.detail_text   = detail[:_MAX_STR - 1]
        self._shared.image_path    = image_path[:_MAX_IMG - 1]
        self._shared.progress_x100 = int(max(0.0, min(100.0, progress)) * 100)
        # Write visible LAST so the DLL sees consistent data
        self._shared.visible = 1

    def update(self, progress: float, detail: str = "") -> None:
        if not self._ready or self._shared is None:
            return
        if detail:
            self._shared.detail_text = detail[:_MAX_STR - 1]
        self._shared.progress_x100 = int(max(0.0, min(100.0, progress)) * 100)

    def show_asset(self, kind: str, name: str, detail: str = "", progress: float = 0.0, image_path: str = "") -> None:
        if not self._ready or self._shared is None:
            return
        if kind not in {"scoreboard", "movie", "narration"}:
            return
        setattr(self._shared, f"{kind}_name", name[:_MAX_STR - 1])
        setattr(self._shared, f"{kind}_detail", detail[:_MAX_STR - 1])
        setattr(self._shared, f"{kind}_progress_x100", int(max(0.0, min(100.0, progress)) * 100))
        if kind == 'narration': self._shared.narration_image_path = image_path[:_MAX_IMG - 1]
        setattr(self._shared, f"{kind}_visible", 1)

    def update_asset(self, kind: str, progress: float, detail: str = "") -> None:
        if not self._ready or self._shared is None or kind not in {"scoreboard", "movie", "narration"}:
            return
        if detail:
            setattr(self._shared, f"{kind}_detail", detail[:_MAX_STR - 1])
        setattr(self._shared, f"{kind}_progress_x100", int(max(0.0, min(100.0, progress)) * 100))

    def hide_asset(self, kind: str) -> None:
        if self._shared is not None and kind in {"scoreboard", "movie", "narration"}:
            setattr(self._shared, f"{kind}_visible", 0)

    def hide(self) -> None:
        if self._shared is not None:
            self._shared.visible = 0

    def reset_injected(self) -> None:
        """Call when FIFA exits so we re-inject on the next launch."""
        with self._lock:
            self._injected_pid = 0

    def destroy(self) -> None:
        self.hide()
        if self._shared is not None:
            self._shared.scoreboard_visible = 0
            self._shared.movie_visible = 0
            self._shared.narration_visible = 0
        if self._shared_ptr:
            try:
                _k32.UnmapViewOfFile(self._shared_ptr)
            except Exception:
                pass
            self._shared_ptr = 0
            self._shared     = None
        if self._hmap:
            try:
                _k32.CloseHandle(self._hmap)
            except Exception:
                pass
            self._hmap = 0
        self._ready = False

    # ── Private ───────────────────────────────────────────────────────────────

    def _open_shared_memory(self) -> None:
        hmap = _k32.CreateFileMappingW(
            _INVALID_HANDLE_VALUE, None, _PAGE_READWRITE,
            0, ctypes.sizeof(_OverlayShared),
            _SHMEM_NAME)
        if not hmap:
            log.error("D3DOverlay: CreateFileMappingW failed (err=%d)",
                      ctypes.get_last_error())
            return

        ptr = _k32.MapViewOfFile(
            hmap, _FILE_MAP_ALL_ACCESS, 0, 0,
            ctypes.sizeof(_OverlayShared))
        if not ptr:
            log.error("D3DOverlay: MapViewOfFile failed (err=%d)",
                      ctypes.get_last_error())
            _k32.CloseHandle(hmap)
            return

        self._hmap       = hmap
        self._shared_ptr = ptr
        self._shared     = _OverlayShared.from_address(ptr)
        # Reset to hidden on startup
        self._shared.visible       = 0
        self._shared.progress_x100 = 0
        self._shared.stadium_name  = ""
        self._shared.detail_text   = ""
        self._shared.image_path    = ""
        self._shared.scoreboard_visible = 0
        self._shared.scoreboard_progress_x100 = 0
        self._shared.scoreboard_name = ""
        self._shared.scoreboard_detail = ""
        self._shared.movie_visible = 0
        self._shared.movie_progress_x100 = 0
        self._shared.movie_name = ""
        self._shared.movie_detail = ""
        self._shared.narration_visible = 0
        self._shared.narration_progress_x100 = 0
        self._shared.narration_name = ""
        self._shared.narration_detail = ""
        self._shared.narration_image_path = ""
        self._ready = True
        log.debug("D3DOverlay: shared memory opened at 0x%X, size=%d",
                  ptr, ctypes.sizeof(_OverlayShared))
