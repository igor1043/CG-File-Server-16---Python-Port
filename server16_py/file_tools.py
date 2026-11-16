from __future__ import annotations

import random
import os
import re
import tempfile
import zlib
import shutil
import subprocess
import sys
import stat
import time
import unicodedata
import zipfile
from pathlib import Path, PureWindowsPath
from .asset_access import restore_asset_inheritance

try:
    import rarfile as _rarmod
    if sys.platform == "win32" and getattr(_rarmod, "BSDTAR_TOOL", "") == "bsdtar":
        _rarmod.BSDTAR_TOOL = "tar"
except ImportError:
    _rarmod = None


def _rar_extractors() -> list[tuple[str, str]]:
    tools = []
    for kind, executable, relative in (
        ('UnRAR', 'unrar', 'WinRAR/UnRAR.exe'),
        ('7-Zip', '7z', '7-Zip/7z.exe'),
    ):
        candidates = [shutil.which(executable)]
        for variable in ('ProgramW6432', 'ProgramFiles', 'ProgramFiles(x86)'):
            base = os.environ.get(variable)
            if base:
                candidates.append(str(Path(base) / relative))
        for candidate in candidates:
            if candidate and Path(candidate).is_file() and (kind, candidate) not in tools:
                tools.append((kind, candidate))
                break
    tar = shutil.which('tar')
    if tar:
        tools.append(('tar', tar))
    return tools


def _safe_archive_relative(name: str) -> Path:
    normalized = name.replace('\\', '/')
    windows = PureWindowsPath(normalized)
    if windows.drive or windows.root or '..' in windows.parts or ':' in normalized:
        raise RuntimeError(f'Unsafe archive member path: {name}')
    return Path(*windows.parts)


def _check_rar_output(directory: Path, members) -> None:
    for member in members:
        path = directory / _safe_archive_relative(member.filename)
        if member.isdir():
            continue
        if not path.is_file() or path.is_symlink() or path.stat().st_size != member.file_size:
            raise RuntimeError(f'Incomplete extracted RAR member: {member.filename}')
        expected_crc = getattr(member, 'CRC', None)
        if expected_crc is not None:
            crc = 0
            with path.open('rb') as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b''):
                    crc = zlib.crc32(chunk, crc)
            if crc & 0xffffffff != expected_crc:
                raise RuntimeError(f'RAR checksum mismatch: {member.filename}')


def _directory_identity(path: Path) -> tuple[int, int] | None:
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or path.is_symlink() or getattr(info, 'st_file_attributes', 0) & 1024:
        return None
    # Filesystems without a stable file ID use the original copy path.
    return (info.st_dev, info.st_ino) if info.st_ino else None


def _rar_publication_paths(stage: Path) -> list[Path]:
    """Reject links/reparse points before either publication path can run."""
    paths = []
    pending = [stage]
    while pending:
        for path in pending.pop().iterdir():
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 1024:
                raise RuntimeError(f'Extracted link not allowed: {path.name}')
            paths.append(path)
            if stat.S_ISDIR(info.st_mode):
                pending.append(path)
            elif not stat.S_ISREG(info.st_mode):
                raise RuntimeError(f'Unsupported extracted file: {path.name}')
    return sorted(paths)


def _publish_rar_output(stage: Path, dest_dir: Path, paths: list[Path], progress_callback,
                        *, expected_identity=None, publication_callback=None) -> str:
    """Move only a caller-owned empty temp directory; copy is the safe fallback."""
    method, reason = 'copy', 'fast publication not eligible'
    if expected_identity is not None:
        try:
            destination = dest_dir.absolute()
            if (destination.parent != destination and stage.parent.resolve() == destination.parent.resolve()
                    and _directory_identity(destination) == expected_identity
                    and stage.stat().st_dev == expected_identity[0]
                    and not any(destination.iterdir())):
                # Windows cannot rename over an existing directory. Remove only
                # the verified empty temp directory, never a populated tree.
                destination.rmdir()
                try:
                    stage.rename(destination)
                except OSError as exc:
                    destination.mkdir(exist_ok=True)
                    reason = f'rename failed; using validated copy: {exc}'
                else:
                    method, reason = 'rename', 'validated folder renamed on the same volume'
            else:
                reason = 'destination changed, is nonempty, or is on another volume'
        except OSError as exc:
            reason = f'fast publication unavailable; using validated copy: {exc}'

    if method != 'rename':
        dest_dir.mkdir(parents=True, exist_ok=True)
        for index, source in enumerate(paths, 1):
            target = dest_dir / source.relative_to(stage)
            if source.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            if progress_callback:
                progress_callback(index, len(paths), str(source.relative_to(stage)))
    elif progress_callback:
        progress_callback(len(paths), len(paths), 'Validated extraction ready')
    if publication_callback:
        try:
            publication_callback(method, reason)
        except Exception:
            pass  # Diagnostics cannot turn a complete extraction into failure.
    return method


def _extract_rar(archive_path: Path, dest_dir: Path, progress_callback,
                 *, fast_publish: bool = False, publication_callback=None) -> str:
    members = []
    if _rarmod is not None:
        with _rarmod.RarFile(archive_path, 'r') as archive:
            members = archive.infolist()
            for member in members:
                _safe_archive_relative(member.filename)
                if getattr(member, 'file_redir', None) or (hasattr(member, 'is_symlink') and member.is_symlink()):
                    raise RuntimeError(f'RAR links are not allowed: {member.filename}')
    expected_identity = None
    if fast_publish and members:
        try:
            if not any(dest_dir.iterdir()):
                expected_identity = _directory_identity(dest_dir)
        except OSError:
            pass  # Keep the original copy path when eligibility is uncertain.
    errors = []
    # Extract the full archive, not rarfile's synthetic single-file RAR streams:
    # Windows bsdtar returns truncated data for some of those streams. Publish
    # only a complete, size/CRC-checked result from an isolated staging folder.
    for kind, executable in _rar_extractors():
        with tempfile.TemporaryDirectory(prefix='rar_stage_', dir=dest_dir.parent) as temporary:
            stage = Path(temporary)
            if kind == 'UnRAR':
                command = [executable, 'x', '-idq', '-o+', '-p-', '--', str(archive_path.resolve()), str(stage) + os.sep]
            elif kind == '7-Zip':
                command = [executable, 'x', '-y', '-p', '-o' + str(stage), '--', str(archive_path.resolve())]
            else:
                command = [executable, '-xf', str(archive_path.resolve()), '-C', str(stage)]
            if progress_callback:
                progress_callback(0, max(1, len(members)), f'Extracting with {kind}')
            try:
                result = subprocess.run(command, capture_output=True, text=True, errors='replace',
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), timeout=300)
                if result.returncode != 0:
                    raise RuntimeError((result.stderr or result.stdout).strip() or f'exit code {result.returncode}')
                paths = _rar_publication_paths(stage)
                _check_rar_output(stage, members)
                if not any(path.is_file() for path in paths):
                    raise RuntimeError('RAR extraction produced no files')
            except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
                errors.append(f'{kind}: {exc}')
                continue
            _publish_rar_output(stage, dest_dir, paths, progress_callback,
                                expected_identity=expected_identity, publication_callback=publication_callback)
            return kind
    details = '; '.join(errors) or 'Install WinRAR (UnRAR) or 7-Zip; no RAR extractor was found'
    raise RuntimeError(f'Failed to extract RAR {archive_path.name}: {details}')

try:
    from win32api import GetFileVersionInfo, HIWORD, LOWORD
except Exception:
    GetFileVersionInfo = None
    HIWORD = LOWORD = None


STADIUM_ARCHIVE_SUFFIXES = {".zip", ".rar"}
STADIUM_PREVIEW_SUFFIXES = {".png", ".jpg", ".jpeg", ".jepg"}


def _normalized_lookup_name(value: str) -> str:
    return unicodedata.normalize("NFC", value or "").casefold()


def stadium_preview_dir(stadium_gbd: str | Path) -> Path:
    return Path(stadium_gbd) / "render" / "thumbnail" / "stadium"


def resolve_stadium_preview_path(stadium_gbd: str | Path, stadium_name: str) -> Path | None:
    stadium_name = (stadium_name or "").strip()
    if not stadium_name or stadium_name in {"-", "None", "Stadium Module Disable"}:
        return None
    preview_dir = stadium_preview_dir(stadium_gbd)
    if not preview_dir.exists():
        return None

    lookup_names = [stadium_name]
    stadium_suffix = Path(stadium_name).suffix.lower()
    if stadium_suffix in STADIUM_ARCHIVE_SUFFIXES:
        stem_name = Path(stadium_name).stem.strip()
        if stem_name:
            lookup_names.append(stem_name)

    for lookup_name in lookup_names:
        for suffix in sorted(STADIUM_PREVIEW_SUFFIXES):
            candidate = preview_dir / f"{lookup_name}{suffix}"
            if candidate.is_file():
                return candidate

    wanted = {_normalized_lookup_name(name) for name in lookup_names}
    for candidate in sorted(preview_dir.iterdir(), key=lambda path: path.name.lower()):
        if not candidate.is_file() or candidate.suffix.lower() not in STADIUM_PREVIEW_SUFFIXES:
            continue
        if _normalized_lookup_name(candidate.stem) in wanted:
            return candidate
    return None


def discover_stadium_names(stadium_gbd: str | Path) -> list[str]:
    root = Path(stadium_gbd)
    names: dict[str, str] = {}

    def add(name: str) -> None:
        name = (name or "").strip()
        if not name or name == "None":
            return
        names.setdefault(_normalized_lookup_name(name), name)

    if root.exists():
        for item in root.iterdir():
            if item.name.startswith(".") or item.name.casefold() == "render":
                continue
            if item.is_dir():
                add(item.name)
            elif item.is_file() and item.suffix.lower() in STADIUM_ARCHIVE_SUFFIXES:
                add(item.stem)

    previews = stadium_preview_dir(root)
    if previews.exists():
        for item in previews.iterdir():
            if item.is_file() and item.suffix.lower() in STADIUM_PREVIEW_SUFFIXES:
                add(item.stem)

    return sorted(names.values(), key=lambda value: _normalized_lookup_name(value))


def is_archive(path: Path) -> bool:
    suffix = path.suffix.lower()
    return suffix in STADIUM_ARCHIVE_SUFFIXES


def extract_archive(archive_path: Path, dest_dir: Path, progress_callback=None,
                    *, fast_publish: bool = False, publication_callback=None) -> str:
    suffix = archive_path.suffix.lower()
    dest_dir.mkdir(parents=True, exist_ok=True)
    if suffix == ".zip":
        with zipfile.ZipFile(archive_path, "r") as zf:
            members = zf.infolist()
            total = len(members)
            for index, member in enumerate(members, start=1):
                _safe_archive_relative(member.filename)
                zf.extract(member, dest_dir)
                if progress_callback:
                    progress_callback(index, total, member.filename)
        return 'ZIP'
    elif suffix == ".rar":
        return _extract_rar(archive_path, dest_dir, progress_callback,
                            fast_publish=fast_publish, publication_callback=publication_callback)
    else:
        raise RuntimeError(f"Unsupported archive format: {archive_path.suffix}")


def checkdirs(path: str | Path) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)


def ensure_server16_asset_access(path: str | Path, log=None) -> bool:
    """Check a managed directory without changing ownership or Windows ACLs.

    Compatibility entry point for callers outside the normal copy flow. Write
    permission and permission to change an ACL are different Windows rights.
    An ordinary asset copy must never require the latter.
    """
    asset_root = Path(path)
    if not asset_root.is_dir():
        return True
    try:
        with tempfile.TemporaryFile(prefix='.server16-access-', dir=asset_root) as probe:
            probe.write(b'Server16')
            probe.flush()
    except OSError as exc:
        if callable(log):
            log(f'Asset destination is not writable by the current user: {asset_root}', exc)
        return False
    return True


def ensure_server16_stadium_access(sceneassets_dir: str | Path, log=None) -> None:
    """Restore parent inheritance only on known stadium destinations.

    Legacy glare files can have a protected ACL even when the installation is
    writable. Include fx and both injection slots; never reset a whole tree.
    """
    root = Path(sceneassets_dir)
    for name in ('stadium', 'crowdplacement', 'crowdchair', 'fx'):
        target = root / name
        if target.is_dir():
            restore_asset_inheritance(target, log=log)
            ensure_server16_asset_access(target, log=log)
    for slot in ('176', '261'):
        for relative in sorted(stadium_injection_paths(slot)):
            target = root / relative
            if target.is_file():
                restore_asset_inheritance(target, log=log)


def _asset_directory(path: Path) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        existing = path
        while not existing.exists() and existing != existing.parent:
            existing = existing.parent
        if not restore_asset_inheritance(existing):
            raise
        path.mkdir(parents=True, exist_ok=True)


def _files_match(src: Path, dst: Path) -> bool:
    try:
        if not dst.exists() or not dst.is_file():
            return False
        src_stat = src.stat()
        dst_stat = dst.stat()
        if src_stat.st_size != dst_stat.st_size or src_stat.st_mtime_ns != dst_stat.st_mtime_ns:
            return False
        # ZIPs can give different BIG/RX3/VP8 payloads identical sizes and
        # timestamps. Metadata alone cannot decide that a swap is unnecessary.
        with src.open('rb') as left, dst.open('rb') as right:
            while True:
                chunk = left.read(1024 * 1024)
                if chunk != right.read(1024 * 1024):
                    return False
                if not chunk:
                    return True
    except Exception:
        return False


def _copy_file_if_needed(src: Path, dst: Path) -> bool:
    _asset_directory(dst.parent)
    if _files_match(src, dst):
        make_asset_writable(dst)
        return False
    copy_asset_file(src, dst)
    return True


def copy_asset_file(src: str | Path, dst: str | Path) -> None:
    """Publish a full copy, including when package timestamps are identical."""
    src, dst = Path(src), Path(dst)
    _asset_directory(dst.parent)
    # New files inherit the destination directory's permissions. Never import
    # source ACLs or leave half of a BIG/RX3 published after a failed copy.
    try:
        handle, temporary = tempfile.mkstemp(prefix='.server16-', suffix='.tmp', dir=dst.parent)
    except PermissionError:
        if not restore_asset_inheritance(dst.parent):
            raise
        handle, temporary = tempfile.mkstemp(prefix='.server16-', suffix='.tmp', dir=dst.parent)
    os.close(handle)
    staged = Path(temporary)
    try:
        shutil.copy2(src, staged)
        make_asset_writable(staged)
        replace_asset_file(staged, dst)
    finally:
        if staged.exists():
            make_asset_writable(staged)
            staged.unlink()


def make_asset_writable(path: str | Path) -> None:
    """Clear only a file's DOS read-only bit, without altering its Windows ACL."""
    path = Path(path)
    info = path.stat()
    if os.name == 'nt' and getattr(info, 'st_file_attributes', 0) & 1:
        try:
            path.chmod(info.st_mode | stat.S_IWRITE)
        except PermissionError:
            if not restore_asset_inheritance(path):
                raise
            path.chmod(info.st_mode | stat.S_IWRITE)


def replace_asset_file(src: str | Path, dst: str | Path, *, source_owned: bool = False) -> None:
    """Replace one managed asset, allowing bounded transient sharing conflicts."""
    src, dst = Path(src), Path(dst)
    repaired = False
    for attempt in range(4):
        try:
            os.replace(src, dst)
            return
        except PermissionError as exc:
            if dst.is_file() and os.name == 'nt' and dst.stat().st_file_attributes & 1:
                make_asset_writable(dst)
                continue
            if getattr(exc, 'winerror', None) == 5 and not repaired:
                repaired = True
                changed = restore_asset_inheritance(dst)
                if source_owned:
                    changed = restore_asset_inheritance(src) or changed
                if not changed:
                    changed = restore_asset_inheritance(dst.parent)
                if changed:
                    continue
            # A scanner or a game file handle can briefly hold a sharing lock.
            # An actual ACL/security-policy denial is not retried or elevated.
            if getattr(exc, 'winerror', None) in (32, 33) and attempt < 3:
                time.sleep((.05, .15, .3)[attempt])
                continue
            raise PermissionError(
                f'Não foi possível substituir o arquivo {dst}. '
                f'Verifique a permissão de gravação da pasta e se o arquivo está em uso. ({exc})'
            ) from exc
    raise PermissionError(f'Não foi possível substituir o arquivo {dst}; o destino permaneceu bloqueado')


def copy(src: str | Path, dst: str | Path, progress_callback=None) -> None:
    src_path = Path(src)
    dst_path = Path(dst)
    _asset_directory(dst_path)
    if not src_path.exists():
        return
    if src_path.is_file():
        target = dst_path if dst_path.suffix else dst_path / src_path.name
        _copy_file_if_needed(src_path, target)
        if progress_callback:
            progress_callback(1, 1, src_path.name)
        return
    items = [item for item in src_path.rglob("*") if item.is_file() and item.suffix.lower() != ".png"]
    total = max(1, len(items))
    completed = 0
    for item in src_path.rglob("*"):
        rel = item.relative_to(src_path)
        target = dst_path / rel
        if item.is_dir():
            _asset_directory(target)
        else:
            if item.suffix.lower() == ".png":
                continue
            _copy_file_if_needed(item, target)
            completed += 1
            if progress_callback:
                progress_callback(completed, total, item.name)


def sync_tree(src: str | Path, dst: str | Path, *, skip_suffixes: set[str] | None = None) -> int:
    src_path = Path(src)
    dst_path = Path(dst)
    suffixes = {suffix.lower() for suffix in (skip_suffixes or set())}
    if not src_path.exists():
        return 0
    if src_path.is_file():
        if src_path.suffix.lower() in suffixes:
            return 0
        return 1 if _copy_file_if_needed(src_path, dst_path) else 0
    dst_path.mkdir(parents=True, exist_ok=True)
    src_entries = {item.name: item for item in src_path.iterdir()}
    for existing in list(dst_path.iterdir()):
        if existing.name in src_entries:
            continue
        if existing.is_dir():
            shutil.rmtree(existing)
        else:
            existing.unlink(missing_ok=True)
    copied = 0
    for name, source_item in src_entries.items():
        target = dst_path / name
        if source_item.is_dir():
            copied += sync_tree(source_item, target, skip_suffixes=suffixes)
        else:
            if source_item.suffix.lower() in suffixes:
                continue
            copied += 1 if _copy_file_if_needed(source_item, target) else 0
    return copied


def copy_or_clear(src: str | Path, dst: str | Path) -> None:
    """Copy a runtime asset when its source exists, otherwise remove the stale target."""
    src_path = Path(src)
    dst_path = Path(dst)
    if src_path.is_file():
        _copy_file_if_needed(src_path, dst_path)
    elif dst_path.is_file():
        try:
            dst_path.unlink(missing_ok=True)
        except PermissionError:
            if not restore_asset_inheritance(dst_path):
                raise
            dst_path.unlink(missing_ok=True)


_STADIUM_INJECTION_FILES = (
    ("stadium", "stadium_{id}.rx3"),
    ("stadium", "stadium_{id}_1_textures.rx3"),
    ("stadium", "stadium_{id}_3_textures.rx3"),
    ("crowdplacement", "crowd_{id}_1.dat"),
    ("crowdplacement", "crowd_{id}_3.dat"),
    ("crowdchair", "specificchair_0_{id}.rx3"),
)


def stadium_injection_paths(inj_id: str) -> set[Path]:
    paths = {Path(relative_dir) / template.format(id=inj_id) for relative_dir, template in _STADIUM_INJECTION_FILES}
    paths.update(Path('fx') / f'glares_{inj_id}_{day_night}_{suffix}.{extension}'
        for suffix in range(4) for day_night in ('1', '3') for extension in ('rx3', 'lnx'))
    return paths


def restore_stadium_inj_files(sceneassets_dir: Path, fsw_stadium_dir: Path, inj_id: str) -> None:
    """Restore one stadium injection slot from the FSW native backup."""
    for relative_dir, filename_template in _STADIUM_INJECTION_FILES:
        filename = filename_template.format(id=inj_id)
        copy_or_clear(
            fsw_stadium_dir / relative_dir / filename,
            sceneassets_dir / relative_dir / filename,
        )
    for suffix in range(4):
        for day_night in ("1", "3"):
            for extension in ("rx3", "lnx"):
                filename = f"glares_{inj_id}_{day_night}_{suffix}.{extension}"
                copy_or_clear(
                    fsw_stadium_dir / "fx" / filename,
                    sceneassets_dir / "fx" / filename,
                )


def restore_native_assets(app) -> int:
    """Restore the loose files managed by the server from the FSW backups.

    This is deliberately limited to the server's known destinations. It does
    not touch the selected FIFA executable or packed game archives.
    """
    exedir = Path(app.exedir)
    fsw = exedir / "FSW"
    ensure_server16_stadium_access(exedir / 'data/sceneassets', log=getattr(app, 'log', None))
    from .stadium_match_assets import clear_match_routes
    clear_match_routes(exedir)
    restored = 0
    tree_pairs = (
        (fsw / "stadium", exedir / "data" / "sceneassets"),
        (fsw / "TVLogo", exedir / "data" / "ui" / "game" / "overlays"),
        (fsw / "ScoreBoard", exedir / "data" / "ui" / "game"),
        (getattr(app, "Psource", fsw / "Police"), exedir / "data" / "sceneassets" / "slc"),
        (getattr(app, "Nsource", fsw / "Nets"), exedir / "data" / "sceneassets" / "goalnet"),
        (getattr(app, "PitchMowsource", fsw / "PitchMowPattern"), exedir / "data" / "sceneassets" / "pitch"),
        (fsw / "bcdata" / "camera", exedir / "data" / "bcdata" / "camera"),
    )
    for source, target in tree_pairs:
        if source.exists():
            copy(source, target)
            restored += sum(1 for item in source.rglob("*") if item.is_file()) if source.is_dir() else 1

    # Navigation and intro files belong to the original bootstrap/movie flow.
    # Replacing them here disables Movies even when its module stays enabled.

    for slot in ("176", "261"):
        restore_stadium_inj_files(
            exedir / "data" / "sceneassets",
            fsw / "Stadium",
            slot,
        )
    return restored


def copy_if_exists(src: str | Path, dst: str | Path) -> None:
    src_path = Path(src)
    if not src_path.exists():
        return
    _copy_file_if_needed(src_path, Path(dst))


def copy_tvlogo(src: str | Path, dst: str | Path) -> str:
    src_path = Path(src)
    if not src_path.exists():
        return "default"
    dst_path = Path(dst)
    dst_path.mkdir(parents=True, exist_ok=True)
    if src_path.is_file():
        _copy_file_if_needed(src_path, dst_path / src_path.name)
        return "default"
    files = sorted(item for item in src_path.iterdir() if item.is_file())
    if not files:
        return "default"
    first_name = files[0].stem
    if "overlay_9105" in first_name:
        _copy_file_if_needed(files[0], dst_path / files[0].name)
        return "default"
    chosen = random.choice(files)
    tvlogo_type = chosen.name.split("_", 1)[0]
    _copy_file_if_needed(chosen, dst_path / "overlay_9105.big")
    return tvlogo_type


def copy_glares(src: str | Path, day_or_night: str, index: str, inj_id: str, exedir: str | Path) -> None:
    src_path = Path(src)
    if not src_path.exists():
        return
    dst = Path(exedir) / "data" / "sceneassets" / "fx" / f"glares_{inj_id}_{day_or_night}_{index}.lnx"
    dst.parent.mkdir(parents=True, exist_ok=True)
    lines = src_path.read_text(encoding="utf-8-sig", errors="ignore").splitlines()
    rewritten: list[str] = []
    for line in lines:
        if 'name="glares' in line:
            parts = line.split("_")
            if len(parts) > 1:
                old_id = parts[1]
                line = line.replace(f"glares_{old_id}", f"glares_{inj_id}", 1)
        rewritten.append(line)
    dst.write_text("\r\n".join(rewritten) + "\r\n", encoding="utf-8")


def extra_setup(source_dir: str | Path, dest_dir: str | Path, source_index: str, asset_prefix: str, dest_index: str, log=None) -> None:
    src_root = Path(source_dir)
    dest_root = Path(dest_dir)
    dest_root.mkdir(parents=True, exist_ok=True)
    if not src_root.exists():
        return
    token = f"_{source_index}"
    replacement = f"_{dest_index}"
    for item in src_root.rglob("*"):
        if not item.is_file():
            continue
        target_name = item.name.replace(token, replacement) if token in item.name else item.name
        if asset_prefix.lower() not in target_name.lower() and asset_prefix not in {"4", "9"}:
            continue
        _copy_file_if_needed(item, dest_root / target_name)


def checkver(_fifa_exe: str) -> str:
    if not _fifa_exe or GetFileVersionInfo is None:
        return "unknown"
    try:
        info = GetFileVersionInfo(_fifa_exe, "\\")
        ms = info["FileVersionMS"]
        ls = info["FileVersionLS"]
        return ".".join(str(part) for part in (HIWORD(ms), LOWORD(ms), HIWORD(ls), LOWORD(ls)))
    except Exception:
        return "unknown"


def inc_count(_count1: int, current: str) -> str:
    return "1" if current == "0" else "0"


def set_inj_id(counter: str) -> tuple[str, str]:
    return ("176", "4") if counter == "0" else ("261", "9")


# Generated preview/import data only.  These folders are safe to remove because
# their callers recreate them on demand; settings, logs, and installed assets
# deliberately do not belong to this cache.
GENERATED_CACHE_SUBDIRS = ("goalpost_texture_previews", "kitmix_previews", "kitmix_imports")


def clear_generated_cache(base_dir: str | Path) -> tuple[int, int]:
    """Remove generated preview/import caches below ``runtime``.

    Returns ``(bytes_freed, folders_removed)``.  A missing cache is a normal
    no-op, while individual files that disappear during cleanup are ignored.
    """
    runtime_dir = Path(base_dir) / "runtime"
    if not runtime_dir.is_dir():
        return 0, 0

    targets = [runtime_dir / name for name in GENERATED_CACHE_SUBDIRS]
    targets.extend(path for path in runtime_dir.glob("server16_stad_*") if path.is_dir())

    bytes_freed = 0
    folders_removed = 0
    for target in targets:
        if not target.is_dir():
            continue
        for path in target.rglob("*"):
            if path.is_file():
                try:
                    bytes_freed += path.stat().st_size
                except OSError:
                    pass
        shutil.rmtree(target, ignore_errors=True)
        if not target.exists():
            folders_removed += 1
    return bytes_freed, folders_removed


def prepare_asset_copy(source: str | Path, destination: str | Path, log=None) -> None:
    """Normalize only protected destinations belonging to this asset package.

    An identical overlay payload can be skipped by the copier while retaining
    a legacy protected DACL. Repair inheritance before the equality shortcut,
    also on the package's existing target folders, using the current token.
    No owner/explicit rule is changed and no privilege/UAC request is made.
    """
    source, destination = Path(source), Path(destination).absolute()
    if not source.is_dir():
        return
    paths = set()
    for item in source.rglob('*'):
        if not item.is_file() or item.suffix.lower() == '.png':
            continue
        relative = item.relative_to(source)
        target = destination / relative
        assert target.is_relative_to(destination)
        current = target
        while current.is_relative_to(destination):
            if current.exists():
                paths.add(current)
            if current == destination:
                break
            current = current.parent
    for path in sorted(paths, key=lambda p: (len(p.parts), str(p))):
        restore_asset_inheritance(path, log=log)
