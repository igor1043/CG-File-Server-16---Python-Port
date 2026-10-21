"""Install only the panorama drone package, preserving every other mod/config."""
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import configparser
import re
import shutil


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def upgrade_config(text, defaults):
    """Upgrade only old defaults and missing shots, retaining user choices/comments."""
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.read_string(text)
    lines = text.splitlines()

    def set_value(section, key, value):
        start = next((i for i, line in enumerate(lines) if line.strip().lower() == f"[{section}]"), None)
        if start is None:
            lines.extend(["", f"[{section}]", f"{key}={value}"])
            return
        end = next((i for i in range(start + 1, len(lines)) if lines[i].lstrip().startswith("[")), len(lines))
        for i in range(start + 1, end):
            if re.match(rf"\s*{re.escape(key)}\s*=", lines[i], re.I):
                lines[i] = f"{key}={value}"
                return
        lines.insert(end, f"{key}={value}")

    main_section = next((s for s in parser.sections() if s.lower() == "panorama_drone"), "panorama_drone")
    shots_section = next((s for s in parser.sections() if s.lower() == "shots"), "shots")
    if parser.getint(main_section, "scene_pack_revision", fallback=0) < 3:
        for key, old, new in (("duration_seconds", 32, 52), ("height_limit_cm", 3200, 11000)):
            if parser.getfloat(main_section, key, fallback=old) == old:
                set_value("panorama_drone", key, new)
    if parser.getint(main_section, "scene_pack_revision", fallback=0) < 6:
        set_value("panorama_drone", "scene_pack_revision", 6)
    default_parser = configparser.ConfigParser(interpolation=None)
    default_parser.read_string(defaults)
    for key, value in default_parser.items("shots"):
        if not parser.has_option(shots_section, key):
            set_value("shots", key, value)
    return "\n".join(lines) + "\n"


def install(build, destinations):
    source = Path(__file__).resolve().parents[1]
    dll = build / "panorama_drone_v5.dll"
    if not dll.is_file():
        raise FileNotFoundError(dll)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    manifest = {"version": 5, "scene_pack_revision": 6, "shots": 39, "dll_sha256": digest(dll), "destinations": []}
    for root in destinations:
        root = root.resolve(strict=True)
        mod = root / "ModCarrerMode"
        if not (mod / "mods/enabled.txt").is_file():
            raise FileNotFoundError(mod / "mods/enabled.txt")
        backup = root / "runtime/backups/panorama_drone" / stamp
        changed = []

        def put(src, target):
            if target.exists():
                if digest(src) == digest(target):
                    return
                old = backup / target.relative_to(root)
                old.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, old)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)
            if digest(src) != digest(target):
                raise RuntimeError(f"Copy verification failed: {target}")
            changed.append(str(target.relative_to(root)))

        put(dll, mod / "mods/panorama_drone/panorama_drone_v5.dll")
        for item in (source / "native_mods/panorama_drone").iterdir():
            if item.is_file():
                put(item, mod / "source/native_mods/panorama_drone" / item.name)
        for relative in ("scripts/build_panorama_drone.cmd", "tests/native_panorama_drone_test.cpp", "tests/test_panorama_drone_install.py", "tools/install_panorama_drone.py"):
            put(source / relative, mod / "source" / relative)
        # Migrate the previous 32s/32m defaults once. Custom settings and all
        # existing shot toggles remain intact; add the new shot switches.
        config = mod / "config/panorama_drone.ini"
        default_config = source / "native_mods/panorama_drone/panorama_drone.ini"
        if not config.exists():
            put(default_config, config)
        else:
            previous_text = config.read_text(encoding="utf-8-sig")
            updated = upgrade_config(previous_text, default_config.read_text(encoding="utf-8-sig"))
            if updated != previous_text:
                old = backup / config.relative_to(root)
                old.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(config, old)
                config.write_text(updated, encoding="utf-8")
                changed.append(str(config.relative_to(root)))
        enabled = mod / "mods/enabled.txt"
        lines = enabled.read_text(encoding="utf-8-sig").splitlines()
        lines = [line for line in lines if not line.strip().replace("/", "\\").lower().startswith("panorama_drone\\")]
        lines.append(r"panorama_drone\panorama_drone_v5.dll")
        text = "\n".join(lines) + "\n"
        if enabled.read_text(encoding="utf-8-sig") != text:
            previous = backup / "ModCarrerMode/mods/enabled.txt"
            previous.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(enabled, previous)
            enabled.write_text(text, encoding="utf-8")
            changed.append("ModCarrerMode/mods/enabled.txt")
        if enabled.read_text(encoding="utf-8").count(r"panorama_drone\panorama_drone_v5.dll") != 1:
            raise RuntimeError("Expected exactly one enabled panorama DLL")
        manifest["destinations"].append({"root": str(root), "backup": str(backup), "changed": changed})
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", required=True, type=Path)
    parser.add_argument("--game", required=True, type=Path)
    parser.add_argument("--development", required=True, type=Path)
    args = parser.parse_args()
    result = install(args.build, [args.game, args.development])
    (args.build / "installation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
