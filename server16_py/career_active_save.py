"""Identify the career FIFA actually read; no newest-file or club-name guesses."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from pathlib import Path


class ActiveCareerUnavailable(ValueError):
    pass


def process_created(memory):
    kernel = getattr(memory, 'kernel32', None)
    handle = getattr(memory, 'process_handle', None)
    if kernel is None or not handle or not memory.is_open():
        raise ActiveCareerUnavailable('Aguardando conexão com o FIFA.')
    function = kernel.GetProcessTimes
    function.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    function.restype = wintypes.BOOL
    values = [wintypes.FILETIME() for _ in range(4)]
    if not function(handle, *(ctypes.byref(value) for value in values)):
        raise ActiveCareerUnavailable('Não foi possível identificar a sessão do FIFA.')
    created = values[0]
    return (created.dwHighDateTime << 32) | created.dwLowDateTime


def read_active_save(game, memory):
    """Accept only a completed Career I/O event from this exact FIFA process."""
    pid = int(getattr(memory, 'process_id', 0))
    created = process_created(memory)
    runtime = Path(game)/'ModCarrerMode/runtime'
    for name in ('career_save_source.tsv', 'career_active_save.tsv'):
        try:
            record = dict(line.split('=', 1) for line in
                          (runtime/name).read_text(encoding='utf-8-sig').splitlines() if '=' in line)
            if (int(record.get('schema', 0)) != 3 or int(record['pid']) != pid
                    or int(record['process_created_100ns']) != created
                    or record.get('save_type') != 'SaveType_Career'
                    or record.get('complete_file') != '1'
                    or record.get('operation') not in ('read', 'write')):
                continue
            path = Path(record['path']).resolve()
            if path.name.upper() != 'DATA' or not (path.parent/'INDEX').is_file():
                continue
            stat = path.stat()
            if stat.st_size != int(record['size_bytes']):
                continue
            with path.open('rb') as stream:
                header = stream.read(160)
            if (len(header) != 160 or header[116:132] != b'SaveType_Career\0'
                    or int.from_bytes(header[136:140], 'little') != 56):
                continue
            title = header[16:80].split(b'\0', 1)[0].decode('utf-8', errors='replace').strip()
            return {'path': str(path), 'title': title or 'Carreira em execução',
                    'slot': path.parent.name, 'pid': pid, 'process_created_100ns': created,
                    'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns}
        except (OSError, ValueError, KeyError, TypeError):
            continue
    raise ActiveCareerUnavailable(
        'Aguardando a carreira em execução. Salve o progresso no FIFA ou reabra a carreira.')


def identity(save):
    return (save['pid'], save['process_created_100ns'], save['path'].casefold())


def version(save):
    return identity(save) + (save['size'], save['mtime_ns'])
