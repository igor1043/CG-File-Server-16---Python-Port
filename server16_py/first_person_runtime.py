"""Server-owned first-person camera channel. No separate panel process."""
from __future__ import annotations
import ctypes
import json
import mmap
import os
import queue
import subprocess
import threading
import time
from pathlib import Path

MAPPING_NAME = 'Local\\FIFA16_FirstPersonCamera_v4'
DLL_NAME = 'server16_first_person_v14.dll'
DEFAULT_FOV = 85
CAREER_FOV = 85
PREFERENCES_VERSION = 4
HEAD_SMOOTHING = ('Média', 'Alta', 'Extra alta', 'Agressiva')


class CameraShared(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint32) for name in
                ('version', 'owner', 'heartbeat', 'command', 'ack', 'ready')] + [
        (name, ctypes.c_int32) for name in
        ('requested', 'profile', 'framing', 'enabled', 'valid', 'selected', 'gameState', 'error')
    ] + [('frames', ctypes.c_uint32), ('applied', ctypes.c_uint32),
         ('fov', ctypes.c_int32), ('look_bias', ctypes.c_int32), ('mode', ctypes.c_int32),
         ('distance', ctypes.c_int32)]


def fov_limits(mode):
    return (60, 90) if mode == 1 else (75, 150)


def _load_settings(path):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}
    enabled = data.get('enabled', False) is True
    mode = data.get('mode', 0)
    mode = mode if type(mode) is int and mode in (0, 1) else 0
    # Migrate the old shared/wide lens to the user's requested 85-degree
    # standard in both modes. Later explicit mode-specific choices survive.
    first = data.get('fov_first_person', DEFAULT_FOV) if data.get('version') == PREFERENCES_VERSION else DEFAULT_FOV
    career = data.get('fov_career', CAREER_FOV) if data.get('version') == PREFERENCES_VERSION else CAREER_FOV
    first = first if type(first) is int and 75 <= first <= 150 else DEFAULT_FOV
    career = career if type(career) is int and 60 <= career <= 90 else CAREER_FOV
    distance = data.get('distance', 0)
    distance = distance if type(distance) is int and 0 <= distance <= 2 else 0
    return enabled, mode, [first, career], distance


def load_preferences(path):
    enabled, mode, fovs, _ = _load_settings(path)
    return enabled, fovs[mode], mode


def load_head_smoothing(path):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        value = data.get('head_smoothing', 0) if isinstance(data, dict) else 0
    except (OSError, ValueError):
        value = 0
    return value if type(value) is int and 0 <= value < len(HEAD_SMOOTHING) else 0


def save_preferences(path, enabled, fov, mode=0, *, other_fov=None, distance=0, head_smoothing=0):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    fovs = [DEFAULT_FOV, CAREER_FOV]
    fovs[mode] = fov
    if other_fov is not None:fovs[1-mode] = other_fov
    temporary.write_text(json.dumps({'version': PREFERENCES_VERSION,
                                     'enabled': enabled, 'mode': mode,
                                     'fov_first_person': fovs[0], 'fov_career': fovs[1],
                                     'distance': distance, 'head_smoothing': head_smoothing}), encoding='utf-8')
    temporary.replace(path)


class FirstPersonRuntime:
    def __init__(self, app):
        self.app = app
        self.path = Path(app.base_dir) / 'runtime' / 'first_person_camera.json'
        self.enabled, self.mode, self._fovs, self.distance = _load_settings(self.path)
        self.profile = load_head_smoothing(self.path)
        self.framing, self.look_bias = 1, 0
        self.mapping = mmap.mmap(-1, ctypes.sizeof(CameraShared), tagname=MAPPING_NAME)
        self.shared = CameraShared.from_buffer(self.mapping)
        if self.shared.owner and self.shared.owner != os.getpid():
            import psutil
            if psutil.pid_exists(self.shared.owner):
                del self.shared
                self.mapping.close()
                raise RuntimeError('Outro Server controla a câmera')
        self.shared.version = 4
        self.shared.owner = os.getpid()
        self.shared.heartbeat = ctypes.windll.kernel32.GetTickCount() & 0xffffffff
        self.shared.requested = int(self.enabled)
        self.shared.profile, self.shared.framing = self.profile, self.framing
        self.shared.fov, self.shared.look_bias = self.fov, self.look_bias
        self.shared.mode = self.mode
        self.shared.distance = self.distance
        self.shared.command = (self.shared.command + 1) & 0xffffffff
        self.game_pid = app._resolve_fifa_pid() if app.memory.is_open() else 0
        self.next_attempt = 0
        self.injecting = False
        self.results = queue.Queue()
        self.error = ''
        self.closed = False
        self._last_tick = time.monotonic()
        self._off_since = None

    def tick(self):
        if self.closed:
            return
        now = time.monotonic()
        self.shared.heartbeat = ctypes.windll.kernel32.GetTickCount() & 0xffffffff
        pid = self.app._resolve_fifa_pid() if self.app.memory.is_open() else 0
        if pid == self.game_pid and pid and self.enabled and now-self._last_tick > 1.5:
            # A stalled Server can expire the native heartbeat. Reaffirm the
            # saved choice instead of treating the watchdog's disable as F10.
            self.shared.requested = 1
            self.shared.command = (self.shared.command + 1) & 0xffffffff
            self._off_since = None
        self._last_tick = now
        if pid != self.game_pid:
            self.game_pid = pid
            self.shared.ready = self.shared.enabled = self.shared.valid = 0
            self.shared.requested = int(self.enabled)
            self.shared.error = 0
            self.shared.command = (self.shared.command + 1) & 0xffffffff
            self.error = ''
            self.next_attempt = 0
            self._off_since = None
        elif (pid and self.enabled and self.shared.ready and not self.shared.error
              and self.shared.ack == self.shared.command and self.shared.requested
              and not self.shared.enabled):
            # F10 is an explicit off switch. Preserve that choice, but never
            # interpret a disconnect, rejected command or process exit as off.
            if self._off_since is None:self._off_since = now
            # ack is published just before the native enabled mirror. Require
            # a stable off state so command acknowledgement cannot erase On.
            if now-self._off_since >= .25:
                self.enabled = False
                self.shared.requested = 0
                try:
                    save_preferences(self.path, self.enabled, self.fov, self.mode,
                                     other_fov=self._fovs[1-self.mode], distance=self.distance,
                                     head_smoothing=self.profile)
                except OSError as exc:
                    self.error = 'Não foi possível salvar a opção da câmera.'
                    self.app.log('First-person preference save failed', exc)
        else:self._off_since = None
        while True:
            try:
                completed_pid, ok, detail = self.results.get_nowait()
            except queue.Empty:
                break
            self.injecting = False
            if completed_pid == self.game_pid:
                self.error = '' if ok else 'Não foi possível conectar a câmera. Confira os logs.'
                if not ok:self.app.log('First-person connection: ' + detail)
        if (pid and self.shared.requested and not self.shared.ready and not self.injecting
                and time.monotonic() >= self.next_attempt):
            resources = Path(getattr(self.app, 'resource_dir', self.app.base_dir))
            self.injecting = True
            self.next_attempt = time.monotonic() + 8
            def connect(target=pid):
                ok, detail = False, ''
                try:
                    from .narration_runtime import narration_dll_loaded
                    if narration_dll_loaded(target, DLL_NAME):
                        ok = True
                    elif not narration_dll_loaded(target, 'BCEnginezf.dll'):
                        raise OSError('BCEngine ainda não carregou; tentando novamente em breve')
                    else:
                        raise OSError('Plugin de câmera não carregado. Instale o mod e reinicie o FIFA.')
                except (OSError, subprocess.TimeoutExpired) as exc:
                    detail = str(exc)
                finally:
                    self.results.put((target, ok, detail))
            threading.Thread(target=connect, name='camera-connect', daemon=True).start()

    @property
    def fov(self):
        return self._fovs[self.mode]

    def configure(self, *, enabled=None, fov=None, mode=None, distance=None, head_smoothing=None):
        if enabled is not None and type(enabled) is not bool:
            raise ValueError('Ativação inválida')
        if mode is not None and (type(mode) is not int or mode not in (0, 1)):
            raise ValueError('Modo de câmera inválido')
        if distance is not None and (type(distance) is not int or not 0 <= distance <= 2):
            raise ValueError('Distância de câmera inválida')
        if head_smoothing is not None and (type(head_smoothing) is not int or not 0 <= head_smoothing < len(HEAD_SMOOTHING)):
            raise ValueError('Suavização da cabeça inválida')
        selected_mode = self.mode if mode is None else mode
        low, high = fov_limits(selected_mode)
        if fov is not None and (type(fov) is not int or not low <= fov <= high):
            raise ValueError(f'Campo de visão deve estar entre {low}° e {high}°')
        selected_enabled = self.enabled if enabled is None else enabled
        selected_fov = self._fovs[selected_mode] if fov is None else fov
        selected_distance = self.distance if distance is None else distance
        selected_profile = self.profile if head_smoothing is None else head_smoothing
        save_preferences(self.path, selected_enabled, selected_fov, selected_mode,
                         other_fov=self._fovs[1-selected_mode], distance=selected_distance,
                         head_smoothing=selected_profile)
        self.enabled, self.mode = selected_enabled, selected_mode
        self._fovs[selected_mode] = selected_fov
        self.distance = selected_distance
        self.profile = selected_profile
        self.shared.profile, self.shared.framing = self.profile, self.framing
        self.shared.fov, self.shared.look_bias = self.fov, self.look_bias
        self.shared.mode = self.mode
        self.shared.distance = self.distance
        self.shared.requested = int(self.enabled)
        self._off_since = None
        self.error = ''
        self.shared.error = 0
        self.shared.command = (self.shared.command + 1) & 0xffffffff

    def status(self):
        if self.error:
            return self.error
        if self.shared.error:
            if self.shared.error == 3:
                return 'Câmera salva; aguardando inicialização do FIFA.'
            return ('Outra câmera está em uso ou esta versão do FIFA não é compatível.'
                    if self.shared.error == 1 else 'A configuração da câmera foi rejeitada.')
        if self.enabled and not self.game_pid:
            return 'Câmera salva; aguardando o FIFA.'
        if self.shared.command != self.shared.ack:
            if not self.shared.ready and not self.shared.requested:
                return 'Câmera original ativa.'
            return 'Conectando câmera…' if self.shared.requested else 'Voltando à câmera original…'
        if not self.shared.enabled:
            return 'Câmera original ativa.'
        name = 'Terceira pessoa' if self.mode else 'Primeira pessoa'
        return name + (' ativa.' if self.shared.valid else ' ligada; aguardando o lance.')

    def close(self):
        self.closed = True
        self.shared.requested = 0
        self.shared.command = (self.shared.command + 1) & 0xffffffff
        self.shared.owner = 0
        del self.shared
        self.mapping.close()


def first_person_runtime(app):
    runtime = getattr(app, '_first_person_runtime', None)
    if runtime is None:
        runtime = FirstPersonRuntime(app)
        app._first_person_runtime = runtime
    return runtime
