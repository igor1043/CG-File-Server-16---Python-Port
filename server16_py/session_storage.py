"""Reclaim only Server16 bundles and disposable native calendar observations."""
from contextlib import closing
from dataclasses import dataclass
from datetime import date
from pathlib import Path
import os
import re
import shutil
import sqlite3
import stat
import tempfile
import time

import psutil

BUDGET_BYTES = 1_000_000_000
OWNED_TEMP = r'%LOCALAPPDATA%\FIFA Friends\Server16Temp'
BUNDLE = re.compile(r'_MEI(\d+)$', re.I)
CALENDAR_SCOPE = re.compile(r'([1-9]\d*)-(\d{17,19})-(\d+)-([0-9a-f]+)$')
CALENDAR_FILE = re.compile(r'(\d{8})(?:\.tsv|\.campaign\.json)(?:\.new)?$')
SERVER_NAMES = {'server16.exe', 'server16python.exe'}
LEGACY_MARKERS = ('server16.ico', 'bin/FifaLibrary16.dll', 'bin/fifa16_narration.dll',
                  'server16_py/assets/startup_baseline.json')


@dataclass
class ExtractionSweep:
    removed: int = 0
    released_bytes: int = 0
    retained_bytes: int = 0
    skipped: int = 0


def plain(info):
    return not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400


def _bundle_size(path):
    """Refuse junctions anywhere in a bundle before recursive deletion."""
    total = 0
    todo = [path]
    while todo:
        with os.scandir(todo.pop()) as entries:
            for entry in entries:
                info = entry.stat(follow_symlinks=False)
                if not plain(info):
                    raise ValueError('Unexpected link in bundle')
                if stat.S_ISDIR(info.st_mode):
                    todo.append(entry.path)
                elif stat.S_ISREG(info.st_mode) and info.st_nlink <= 1:
                    total += info.st_size
    return total


def _process_snapshot():
    paths = set()
    births = {}
    for proc in psutil.process_iter(['pid', 'name', 'create_time', 'exe']):
        try:
            info = proc.info
            if info['create_time']:
                births[str(info['pid'])] = info['create_time']
            executable = info.get('exe')
            if executable:
                paths.update(parent.resolve() for parent in Path(executable).parents
                             if BUNDLE.fullmatch(parent.name))
            name = (info['name'] or '').casefold()
            if name in SERVER_NAMES or name.startswith('python') or name in {'fifa16.exe', 'fifa 16.exe'}:
                folder = proc.environ().get('_PYI_APPLICATION_HOME_DIR')
                if folder:
                    paths.add(Path(folder).resolve())
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            continue
    return paths, births


def sweep_extractions(*, roots=None, dry_run=False, grace=120, snapshot=_process_snapshot):
    """A killed onefile process can leave its extracted payload behind.

    Check both the loader's PID prefix and the active child environment. New
    builds extract under a dedicated directory. A legacy entry in shared Temp
    requires multiple Server16 payload markers before it can be touched.
    """
    from .cache_maintenance import safe

    if roots is None:
        local = os.environ.get('LOCALAPPDATA')
        roots = [(Path(tempfile.gettempdir()), False)]
        if local:
            roots.append((Path(local)/'FIFA Friends'/'Server16Temp', True))
    result = ExtractionSweep()
    try:
        in_use, births = snapshot()
    except (psutil.AccessDenied, OSError):
        result.skipped += 1
        return result
    cutoff = time.time() - grace
    for parent, dedicated in roots:
        parent = Path(parent).absolute()
        if not parent.is_dir() or not safe(parent, parent):
            continue
        try:
            candidates = list(parent.iterdir())
        except OSError:
            result.skipped += 1
            continue
        for folder in candidates:
            match = BUNDLE.fullmatch(folder.name)
            if not match or not safe(parent, folder):
                continue
            try:
                info = folder.lstat()
                if not stat.S_ISDIR(info.st_mode) or not plain(info):
                    continue
                if not dedicated and not all(safe(parent, folder/name) and (folder/name).is_file()
                                             for name in LEGACY_MARKERS):
                    continue
                size = _bundle_size(folder)
                born = getattr(info, 'st_birthtime', info.st_ctime)
                # The C loader names its directory _MEI + PID + unique suffix.
                digits = match[1]
                active_parent = any(created - 1 <= born <= created + grace
                                    for end in range(1, len(digits))
                                    if (created := births.get(digits[:end])) is not None)
                if max(born, info.st_mtime) >= cutoff or folder.resolve() in in_use or active_parent:
                    result.retained_bytes += size
                    continue
                if not dry_run:
                    if folder.resolve().parent != parent.resolve() or not safe(parent, folder):
                        raise ValueError('Bundle moved out of its owned directory')
                    shutil.rmtree(folder)
                result.removed += 1
                result.released_bytes += size
            except (OSError, ValueError, RuntimeError):
                result.skipped += 1
    return result


def _pending_save_owners(root):
    """Only current, unbound native writes can pin an old journal.

    Existing SQLite checkpoints and native receipts are never changed.
    """
    from .cache_maintenance import safe

    folder = root/'ModCarrerMode/runtime/manager_market/save_events'
    if not safe(root, folder):
        raise ValueError('Unsafe native receipt directory')
    pending = set()
    for receipt in folder.glob('*.tsv'):
        if not safe(root, receipt) or receipt.stat().st_size > 16_384:
            raise ValueError('Unreadable native receipt')
        record = dict(line.split('=', 1) for line in receipt.read_text(encoding='utf-8-sig').splitlines()
                      if '=' in line)
        if (record.get('operation'), record.get('complete_file'), record.get('save_type')) != (
                'write', '1', 'SaveType_Career'):
            continue
        owner = (int(record['pid']), int(record['process_created_100ns']))
        path = record['path']
        if path.startswith('\\\\?\\UNC\\'):
            path = '\\\\' + path[8:]
        else:
            path = path.removeprefix('\\\\?\\')
        saved = Path(path)
        if not saved.is_absolute() or saved.name.upper() != 'DATA':
            pending.add(owner)
            continue
        try:
            if saved.stat().st_size != int(record['size_bytes']):
                continue
            with saved.open('rb') as stream:
                header = stream.read(160)
            if len(header) != 160 or header[116:132] != b'SaveType_Career\0':
                pending.add(owner)
                continue
            if int.from_bytes(header[132:136], 'little') != int(record['payload_crc32']):
                continue
            database = saved.with_name('server16_manager_market.sqlite3')
            with closing(sqlite3.connect(database.resolve().as_uri()+'?mode=ro', uri=True, timeout=.1)) as db:
                bound = db.execute('SELECT 1 FROM save_receipts WHERE event_id=? AND pid=? AND created=?',
                                   (receipt.stem, *owner)).fetchone()
            if not bound:
                pending.add(owner)
        except FileNotFoundError:
            if saved.with_name('INDEX').exists():
                pending.add(owner)
        except (OSError, sqlite3.Error):
            pending.add(owner)
    return pending


def finished_calendar_files(root, check=lambda:None, alive=psutil.pid_exists):
    """Recognize native filenames and remove only ended, unpinned scopes."""
    from .cache_maintenance import safe

    root = Path(root)
    parent = root/'ModCarrerMode/runtime/manager_market/league_days'
    if not parent.is_dir() or not safe(root, parent):
        return
    try:
        pending = _pending_save_owners(root)
    except (OSError, KeyError, ValueError):
        return
    for folder in parent.iterdir():
        check()
        match = CALENDAR_SCOPE.fullmatch(folder.name)
        if not match or not folder.is_dir() or not safe(root, folder):
            continue
        pid, created = map(int, match.groups()[:2])
        if (pid, created) in pending or alive(pid):
            continue
        for path in folder.iterdir():
            check()
            match = CALENDAR_FILE.fullmatch(path.name)
            if not match or not safe(root, path):
                continue
            day = int(match[1])
            try:
                date(day//10000, day//100%100, day%100)
                if stat.S_ISREG(path.lstat().st_mode):
                    yield path
            except (OSError, ValueError):
                continue


def prune_committed_calendar(root, entries, through):
    """Only retire exact, consumed versions older than the current career day."""
    from .cache_maintenance import safe

    for (day, path), stamp in tuple(entries.items()):
        if day >= through:
            continue
        if safe(root, path):
            try:
                info = path.lstat()
                if stat.S_ISREG(info.st_mode) and (info.st_mtime_ns, info.st_size) == stamp:
                    path.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                continue
        entries.pop((day, path), None)



def sweep_at_startup():
    import logging
    import threading

    logger = logging.getLogger('server16.storage')
    pause = threading.Event()
    while threading.main_thread().is_alive():
        result = sweep_extractions()
        if result.released_bytes or result.skipped:
            logger.info('Extraction cleanup: %d folders, %d bytes freed, %d skipped',
                        result.removed, result.released_bytes, result.skipped)
        if result.retained_bytes > BUDGET_BYTES:
            logger.warning('Active or recently created extraction bundles occupy %d bytes',
                           result.retained_bytes)
        pause.wait(60)
