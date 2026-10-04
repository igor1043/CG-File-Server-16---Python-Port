"""32-bit worker for regenerating BH entries in FIFA .big files."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _prefer_bundled_site_packages() -> None:
    bundled = Path(sys.executable).resolve().parent / "Lib" / "site-packages"
    if not bundled.is_dir():
        return
    user_site = ""
    try:
        import site
        user_site = str(Path(site.getusersitepackages()).resolve()).casefold()
    except Exception:
        pass
    filtered = []
    for entry in sys.path:
        try:
            resolved = str(Path(entry).resolve()).casefold()
        except Exception:
            resolved = str(entry).casefold()
        if user_site and resolved == user_site:
            continue
        if resolved != str(bundled.resolve()).casefold():
            filtered.append(entry)
    sys.path[:] = [str(bundled), *filtered]


def emit(payload: dict) -> None:
    print(json.dumps(payload), flush=True)


def main() -> None:
    if len(sys.argv) < 3:
        emit({"t": "error", "msg": "Usage: bh_worker.py <dll_path> <game_dir>"})
        raise SystemExit(1)
    dll_path = Path(sys.argv[1])
    game_dir = Path(sys.argv[2])
    if not dll_path.exists():
        emit({"t": "error", "msg": f"DLL not found: {dll_path}"})
        raise SystemExit(1)
    if not game_dir.is_dir():
        emit({"t": "error", "msg": f"Game directory not found: {game_dir}"})
        raise SystemExit(1)

    dll_dir = str(dll_path.parent)
    _prefer_bundled_site_packages()
    if dll_dir not in sys.path:
        sys.path.insert(0, dll_dir)
    os.environ["PATH"] = dll_dir + os.pathsep + os.environ.get("PATH", "")
    try:
        clr = __import__("clr")
        try:
            clr.AddReference(str(dll_path))
        except Exception:
            System = __import__("System")
            System.Reflection.Assembly.LoadFrom(str(dll_path))
            clr.AddReference("FifaLibrary16")
        from FifaLibrary import BhFile  # type: ignore[import]
    except Exception as exc:
        emit({"t": "error", "msg": f"Failed to load FifaLibrary16.dll: {exc}"})
        raise SystemExit(1)

    big_files = sorted(game_dir.glob("*.big"))
    if not big_files:
        emit({"t": "error", "msg": "No .big files found in game directory"})
        raise SystemExit(1)
    emit({"t": "ready"})
    ok = 0
    failed = 0
    for index, big_file in enumerate(big_files, start=1):
        try:
            BhFile.Regenerate(str(big_file), True)
            emit({"t": "progress", "i": index, "total": len(big_files), "file": big_file.name, "ok": True})
            ok += 1
        except Exception as exc:
            emit({"t": "progress", "i": index, "total": len(big_files), "file": big_file.name, "ok": False, "error": str(exc)})
            failed += 1
    emit({"t": "done", "ok": ok, "failed": failed})


if __name__ == "__main__":
    main()
