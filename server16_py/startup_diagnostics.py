"""External, read-only startup evidence. Never injects or repairs game files."""
from __future__ import annotations
import ctypes
import hashlib
import json
import os
import platform
import struct
import sys
import threading
import time
import zipfile
from datetime import datetime
from pathlib import Path, PureWindowsPath

import psutil
from .memory_access import MODULEENTRY32W


def log_paths(root):
    root = Path(root)
    paths = list((root/'ModCarrerMode/logs').glob('*.log'))
    return sorted(set(paths + [root/'runtime/server16.log', root/'ReShade.log']))


def log_marker(path):
    try:
        with Path(path).open('rb') as stream:
            stat = os.fstat(stream.fileno())
            stream.seek(max(0, stat.st_size-64))
            return {'offset': stat.st_size, 'identity': stat.st_ino,
                    'anchor': stream.read(64).hex()}
    except OSError:
        return {'offset': 0, 'identity': None, 'anchor': ''}


def session_log(path, marker, limit=1048576):
    """Return only this session's appended bytes, including rotated logs."""
    with Path(path).open('rb') as stream:
        stat = os.fstat(stream.fileno()); start = marker.get('offset', 0)
        rotated = marker.get('identity') not in (None, stat.st_ino) or stat.st_size < start
        if start and not rotated:
            anchor = bytes.fromhex(marker.get('anchor', ''))
            stream.seek(max(0, start-len(anchor)))
            rotated = stream.read(len(anchor)) != anchor
        if rotated:
            start = 0
        at = max(start, stat.st_size-limit)
        stream.seek(at)
        return stream.read(limit), {'start_offset': start, 'end_offset': stat.st_size,
                                    'rotated_or_truncated': rotated, 'tail_limited': at > start}


def crash_summary(path):
    """Read minidump metadata only; the faulting module is not proof of cause."""
    result = {}
    try:
        with Path(path).open('rb') as stream:
            header = stream.read(32)
            if header[:4] != b'MDMP' or len(header) != 32:
                return {'format': 'unrecognized'}
            count, directory = struct.unpack_from('<II', header, 8)
            if count > 128:
                return {'format': 'minidump', 'metadata': 'stream count unsupported'}
            def read(at, size):
                if at < 0 or size > 1048576:
                    raise ValueError('Unsupported minidump metadata size')
                stream.seek(at); data = stream.read(size)
                if len(data) != size:
                    raise ValueError('Incomplete minidump metadata')
                return data
            entries = read(directory, count*12)
            streams = {kind:(size,at) for kind,size,at in struct.iter_unpack('<III', entries)}
            result['format'] = 'minidump'
            if 15 in streams and streams[15][0] >= 12:
                misc = read(streams[15][1], 12)
                if struct.unpack_from('<I', misc, 4)[0] & 1:
                    result['pid'] = struct.unpack_from('<I', misc, 8)[0]
            if 6 in streams and streams[6][0] >= 40:
                exception = read(streams[6][1], 40)
                result['exception_code'] = f'0x{struct.unpack_from("<I", exception, 8)[0]:08x}'
                fault = struct.unpack_from('<Q', exception, 24)[0]
                result['fault_address'] = hex(fault)
                if 4 in streams:
                    at = streams[4][1]; modules = struct.unpack('<I', read(at,4))[0]
                    if modules > 4096:
                        raise ValueError('Module count unsupported')
                    for i in range(modules):
                        base,size,_,_,name_at = struct.unpack('<QIIII', read(at+4+i*108,24))
                        if base <= fault < base+size:
                            length = struct.unpack('<I',read(name_at,4))[0]
                            result['fault_module'] = read(name_at+4,min(length,8192)).decode('utf-16le',errors='replace')
                            result['fault_rva'] = hex(fault-base)
                            break
    except (OSError, ValueError, struct.error) as exc:
        result['metadata_error'] = str(exc)
    return result


def file_evidence(path, with_hash=True):
    path = Path(path)
    try:
        stat = path.stat()
        result = {'bytes': stat.st_size, 'mtime_ns': stat.st_mtime_ns}
        with path.open('rb') as stream:
            head = stream.read(64)
            if head[:2] == b'MZ' and len(head) == 64:
                offset = struct.unpack_from('<I', head, 60)[0]
                if 64 <= offset <= min(stat.st_size - 24, 1048576):
                    stream.seek(offset)
                    pe = stream.read(24)
                    if pe[:4] == b'PE\0\0':
                        result['pe_timestamp'] = hex(struct.unpack_from('<I', pe, 8)[0])
            if with_hash:
                stream.seek(0)
                digest = hashlib.sha256()
                for chunk in iter(lambda: stream.read(1048576), b''):
                    digest.update(chunk)
                result['sha256'] = digest.hexdigest()
        return result
    except OSError as exc:
        return {'error': type(exc).__name__, 'detail': str(exc)}


def audit_files(root, reference, stopped=lambda: False):
    root = Path(root).resolve()
    results = []
    for entry in reference.get('files', []):
        if stopped():
            break
        relative = entry['path']
        relative_path = PureWindowsPath(relative)
        # Refuse traversal in reference data. Installed mod folders may be
        # legitimate junctions to the development tree, so preserve those.
        if relative_path.drive or relative_path.root or '..' in relative_path.parts:
            results.append({'path': relative, 'status': 'invalid_reference'})
            continue
        target = root / relative
        actual = file_evidence(target)
        if 'error' in actual:
            status = 'missing' if actual['error'] == 'FileNotFoundError' else 'unreadable'
        else:
            status = 'match' if actual['sha256'] == entry['sha256'] else 'different'
        results.append({'path': relative, 'role': entry.get('role', 'release'),
                        'status': status, 'expected_sha256': entry['sha256'], 'actual': actual})
    return results


def module_snapshot(pid):
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [ctypes.c_ulong, ctypes.c_ulong]
    kernel.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    kernel.Module32FirstW.argtypes = [ctypes.c_void_p, ctypes.POINTER(MODULEENTRY32W)]
    kernel.Module32NextW.argtypes = kernel.Module32FirstW.argtypes
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.CreateToolhelp32Snapshot(0x18, pid)
    if handle == ctypes.c_void_p(-1).value:
        raise OSError(ctypes.get_last_error(), 'Module snapshot unavailable')
    result = []
    try:
        entry = MODULEENTRY32W(); entry.dwSize = ctypes.sizeof(entry)
        valid = kernel.Module32FirstW(handle, ctypes.byref(entry))
        while valid:
            result.append({'name': entry.szModule, 'path': entry.szExePath,
                           'base': hex(ctypes.cast(entry.modBaseAddr, ctypes.c_void_p).value or 0),
                           'image_bytes': entry.modBaseSize})
            valid = kernel.Module32NextW(handle, ctypes.byref(entry))
        if not result:
            raise OSError(ctypes.get_last_error(), 'Empty module snapshot')
    finally:
        kernel.CloseHandle(handle)
    return result


def version_info(path):
    try:
        api = ctypes.WinDLL('version', use_last_error=True)
        api.GetFileVersionInfoSizeW.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p]
        api.GetFileVersionInfoW.argtypes = [ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p]
        api.VerQueryValueW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_uint)]
        size = api.GetFileVersionInfoSizeW(str(path), None)
        if not 0 < size <= 1048576:
            return {}
        data = ctypes.create_string_buffer(size)
        if not api.GetFileVersionInfoW(str(path), 0, size, data):
            return {}
        pointer = ctypes.c_void_p(); length = ctypes.c_uint()
        result = {}
        if api.VerQueryValueW(data, '\\', ctypes.byref(pointer), ctypes.byref(length)) and length.value >= 16:
            values = ctypes.cast(pointer, ctypes.POINTER(ctypes.c_uint32))
            high, low = values[2], values[3]
            result['version'] = f'{high>>16}.{high&65535}.{low>>16}.{low&65535}'
        language, codepage = 0x409, 0x4b0
        if api.VerQueryValueW(data, '\\VarFileInfo\\Translation', ctypes.byref(pointer), ctypes.byref(length)) and length.value >= 4:
            pair = ctypes.cast(pointer, ctypes.POINTER(ctypes.c_ushort))
            language, codepage = pair[0], pair[1]
        for name in ('ProductName', 'CompanyName', 'FileDescription'):
            key = f'\\StringFileInfo\\{language:04x}{codepage:04x}\\{name}'
            if api.VerQueryValueW(data, key, ctypes.byref(pointer), ctypes.byref(length)) and length.value:
                result[name] = ctypes.wstring_at(pointer, min(length.value, 256)).rstrip('\0')
        return result
    except (OSError, ValueError):
        return {}


class StartupSession:
    def __init__(self, folder, pid, executable, reference, version, markers=None):
        self.folder = Path(folder); self.folder.mkdir(parents=True, exist_ok=False)
        self.pid = pid; self.root = Path(executable).resolve().parent
        self.reference = reference; self.version = version
        self.started_wall = time.time()
        self.log_markers = markers if markers is not None else {str(p):log_marker(p) for p in log_paths(self.root)}
        self.stopped = threading.Event(); self.lock = threading.RLock()
        self.started = time.monotonic(); self.page = ''; self.errors = 0
        self.page_at = self.started
        self.events = 0; self.state = {'pid': pid, 'server_version': version,
            'executable': str(executable), 'reference_release': reference.get('release'),
            'reference_files': len(reference.get('files', [])), 'audit_available': bool(reference.get('files')),
            'last_page': '', 'status': 'watching'}
        self.thread = threading.Thread(target=self.run, name=f'FIFA-startup-evidence-{pid}', daemon=True)

    def event(self, event_type, **data):
        try:
            with self.lock:
                # Bound disk usage without dropping terminal evidence.
                if self.events >= 10000 and event_type not in ('process_exit', 'server_closed', 'diagnostic_error'):
                    return
                row = {'time': datetime.now().astimezone().isoformat(timespec='milliseconds'),
                       'elapsed_s': round(time.monotonic()-self.started, 3), 'pid': self.pid,
                       'event': event_type, **data}
                with (self.folder/'timeline.jsonl').open('a', encoding='utf8') as stream:
                    stream.write(json.dumps(row, ensure_ascii=False)+'\n')
                self.events += 1
        except OSError:
            pass

    def save(self, name, data):
        with self.lock:
            path = self.folder/name; temp = path.with_suffix(path.suffix+'.tmp')
            temp.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
            os.replace(temp, path)

    def page_seen(self, page=None, error=None):
        with self.lock:
            if error is not None:
                self.errors += 1
                if self.errors == 1 or self.errors % 20 == 0:
                    self.event('page_read_pending', attempts=self.errors, detail=str(error)[:500])
            elif page != self.page:
                self.event('page', previous=self.page, current=page, pending_reads=self.errors)
                self.page = page; self.errors = 0; self.state['last_page'] = page
                self.page_at = time.monotonic()
                self.save('summary.json', self.state)

    def capture_modules(self, known):
        modules = module_snapshot(self.pid)
        for item in modules:
            key = (item['path'].casefold(), item['base'])
            if key in known:
                continue
            path = Path(item['path'])
            local = path.is_relative_to(self.root)
            item.update(file_evidence(path, with_hash=local), **version_info(path))
            expected = self.reference.get('loaded_dlls', {}).get(item['name'].lower())
            if expected:
                actual = item.get('sha256') or file_evidence(path).get('sha256')
                item['expected_sha256'] = expected
                item['reference_status'] = 'match' if actual == expected else 'different_or_unreadable'
            item['in_game_directory'] = local
            known[key] = item
            self.event('module_loaded', **item)
        self.save('modules.json', list(known.values()))
        extras = [m['path'] for m in known.values() if m.get('in_game_directory') and
                  m['name'].lower() in ('dxgi.dll','d3d11.dll','d3d9.dll','opengl32.dll')]
        self.state['extra_graphics_dlls'] = extras

    def finish(self):
        self.state['page_read_pending'] = self.errors
        self.state['last_page_elapsed_s'] = round(time.monotonic()-self.page_at, 3)
        collected = []
        for path in log_paths(self.root):
            try:
                contents, window = session_log(path, self.log_markers.get(str(path), {}))
                category = 'server' if path.name == 'server16.log' else 'graphics' if path.name == 'ReShade.log' else 'mods'
                destination = self.folder/'logs'/category/path.name
                destination.parent.mkdir(parents=True,exist_ok=True)
                destination.write_bytes(contents)
                collected.append({'source':str(path),'file':destination.relative_to(self.folder).as_posix(),
                                  'bytes':len(contents), **window})
            except OSError:
                pass
        self.save('logs.json',collected)
        dumps = []
        for path in sorted(self.root.glob('*.dmp')):
            try:
                if path.stat().st_mtime < self.started_wall-2:
                    continue
                entry = {'path':str(path), **file_evidence(path), **crash_summary(path)}
                if entry.get('pid',self.pid) != self.pid:
                    continue
                entry['association'] = 'matching_pid' if 'pid' in entry else 'same_session_time_only'
                if path.stat().st_size <= 16777216:
                    destination=self.folder/'crash'/path.name
                    destination.parent.mkdir(exist_ok=True)
                    with path.open('rb') as stream:
                        data=stream.read(16777217)
                    if len(data)<=16777216:
                        destination.write_bytes(data)
                        entry['included_file']=destination.relative_to(self.folder).as_posix()
                dumps.append(entry)
            except OSError:
                pass
        self.state['crash_dumps']=dumps
        self.state['log_files']=len(collected)
        self.state['session_id']=self.folder.name
        self.save('summary.json', self.state)
        mismatches = self.state.get('file_issues', [])
        text = [f'Diagnóstico FIFA16 / Server16 {self.version}', f'Sessão: {self.folder.name}',f'PID: {self.pid}',
                f'Estado: {self.state["status"]}', f'Última tela: {self.page or "ainda indisponível"}',
                f'Saída do processo: {self.state.get("exit_code", "não observada")}',
                f'Arquivos de referência: {len(self.reference.get("files", []))}',
                'Comparação: disponível' if self.state.get('audit_available') else 'ATENÇÃO: referência ausente; arquivos não foram validados',
                f'Ausências/divergências: {len(mismatches)}',
                'Diferença de arquivo ou DLL extra é evidência para investigar, não prova de causa.', '',
                f'Logs separados por mod: {len(collected)} arquivos em logs/.',
                'Dump desta sessão: '+(', '.join(Path(d['path']).name for d in dumps) or 'não encontrado na pasta do jogo; enviar manualmente com este ZIP'),
                *[f'Falha registrada: {d.get("exception_code","?")} em {d.get("fault_module","módulo não identificado")} + {d.get("fault_rva","?")}' for d in dumps], '',
                'DLLs gráficas extras na pasta do jogo:', *self.state.get('extra_graphics_dlls', []), '',
                'Arquivos para conferir:', *[f'{r["status"]}: {r["path"]} ({r["role"]})' for r in mismatches], '',
                'Enviar este ZIP com o crash.dmp da mesma tentativa. Não inclui saves nem arquivos de configuração com credenciais.']
        (self.folder/'LEIA-ME.txt').write_text('\n'.join(text)+'\n', encoding='utf8')
        archive = self.folder.with_suffix('.zip'); temporary = archive.with_suffix('.zip.tmp')
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as zipped:
            for file in sorted(self.folder.rglob('*')):
                if file.is_file() and not file.name.endswith('.tmp'):
                    zipped.write(file, file.relative_to(self.folder))
        os.replace(temporary, archive)

    def run(self):
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.OpenProcess(0x101000, False, self.pid)  # synchronize + query limited; no VM write/read
        try:
            self.event('session_start', executable=str(self.root), server_version=self.version,
                       windows=platform.platform(), architecture=platform.machine(), reference_release=self.reference.get('release'))
            self.state['server_executable'] = {'path': sys.executable, **file_evidence(sys.executable)}
            self.save('summary.json', self.state)
            known = {}
            try:
                self.capture_modules(known)
            except OSError as exc:
                self.event('module_snapshot_error', detail=str(exc))
            results = audit_files(self.root, self.reference, self.stopped.is_set)
            self.save('files.json', results)
            self.state['audit_complete'] = len(results) == len(self.reference.get('files', []))
            self.state['file_issues'] = [{'path':r['path'], 'role':r.get('role','release'), 'status':r['status']}
                                       for r in results if r['status'] != 'match']
            self.event('file_audit', checked=len(results), issues=self.state['file_issues'])
            while True:
                if handle and kernel.WaitForSingleObject(handle, 0) == 0:
                    code = ctypes.c_ulong()
                    if kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
                        self.state['exit_code'] = f'0x{code.value:08x}'
                    self.state['status'] = 'process_exit_observed'
                    self.event('process_exit', exit_code=self.state.get('exit_code'), last_page=self.page)
                    break
                if not handle and not psutil.pid_exists(self.pid):
                    self.state['status'] = 'process_exit_code_unavailable'
                    self.event('process_exit', last_page=self.page, exit_code=None)
                    break
                if self.stopped.is_set():
                    break
                try:
                    self.capture_modules(known)
                except OSError as exc:
                    self.event('module_snapshot_error', detail=str(exc))
                try:
                    info = psutil.Process(self.pid).memory_info()
                    self.state['resources'] = {'working_set_bytes': info.rss, 'virtual_bytes': info.vms,
                                               'available_ram_bytes': psutil.virtual_memory().available}
                except psutil.Error:
                    pass
                self.save('summary.json', self.state)
                self.stopped.wait(2 if time.monotonic()-self.started < 180 else 15)
            if self.stopped.is_set() and not self.state['status'].startswith('process_exit'):
                self.state['status'] = 'server_closed_process_exit_not_inferred'
                self.event('server_closed', last_page=self.page)
        except Exception as exc:
            self.state['diagnostic_error'] = f'{type(exc).__name__}: {exc}'
            self.event('diagnostic_error', detail=self.state['diagnostic_error'])
        finally:
            if handle:
                kernel.CloseHandle(handle)
            try:
                self.finish()
            except Exception as exc:
                self.event('diagnostic_error', detail=f'Finalization: {exc}')


class StartupDiagnostics:
    def __init__(self, base_dir, resource_dir, version, log):
        self.directory = Path(base_dir)/'runtime/diagnostics'
        self.directory.mkdir(parents=True, exist_ok=True)
        self.version = version; self.log = log; self.sessions = {}; self.current = None
        self.pending_markers = None
        try:
            path = Path(resource_dir)/'server16_py/assets/startup_baseline.json'
            self.reference = json.loads(path.read_text(encoding='utf8'))
        except (OSError, ValueError) as exc:
            self.reference = {'files': []}
            self.log(f'Startup diagnostics: reference unavailable ({exc}); module/page evidence remains enabled')

    def prepare_launch(self, executable):
        """Called before Popen, never truncate a log while FIFA is running."""
        try:
            if self.current and self.current.thread.is_alive():
                self.current.stopped.set(); self.current.thread.join(3)
                if self.current.thread.is_alive():
                    self.log('Startup diagnostics: previous session still finalizing; active logs were preserved')
                    return
            root=Path(executable).resolve().parent
            for path in log_paths(root):
                if path.is_file():
                    try:
                        path.write_bytes(b'')
                    except OSError as exc:
                        self.log(f'Startup diagnostics: could not reset {path.name}: {exc}')
            self.pending_markers={str(p):log_marker(p) for p in log_paths(root)}
            self.current=None
        except Exception as exc:
            self.log(f'Startup diagnostics: log reset unavailable: {exc}')

    def attach(self, pid, executable):
        try:
            if not pid:
                return
            key = (pid, psutil.Process(pid).create_time())
            if key in self.sessions:
                return
            folder = self.directory/(datetime.now().strftime('%Y%m%d_%H%M%S_%f')+f'_pid{pid}')
            session = StartupSession(folder, pid, executable, self.reference, self.version,self.pending_markers)
            self.pending_markers=None
            self.sessions[key] = self.current = session
            session.thread.start()
            self.log(f'Startup diagnostics: PID {pid}; report and automatic ZIP in {folder}')
        except Exception as exc:
            self.log(f'Startup diagnostics unavailable: {exc}')

    def page_seen(self, page=None, error=None):
        try:
            if self.current:
                self.current.page_seen(page, error)
        except Exception:
            pass  # Diagnostics must never interrupt gameplay/polling.

    def close(self):
        for session in self.sessions.values():
            session.stopped.set()
        deadline = time.monotonic()+2
        for session in self.sessions.values():
            session.thread.join(max(0, deadline-time.monotonic()))
