"""Live intro-music profile channel for the resident FIFA audio hook."""
from __future__ import annotations

import ctypes
import json
import mmap
import os
import time
from pathlib import Path

MAPPING_NAME = 'Local\\FIFA16_IntroMusic_v1'


class IntroMusicShared(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint32) for name in (
        'version', 'owner', 'heartbeat', 'command', 'ack', 'ready',
        'phase', 'status', 'error', 'reads', 'replaced', 'hook_calls',
        'description_reads', 'sbs_paths', 'music_paths',
    )] + [('last_path', ctypes.c_wchar * 256), ('package', ctypes.c_wchar * 1024)]


def _settings(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


class IntroMusicRuntime:
    """Select the configured external SPS profile before match kickoff."""

    def __init__(self, app):
        self.app = app
        self.root = Path(getattr(app, 'exedir', app.base_dir)) / 'IntroMusic'
        self.settings_path = self.root / 'settings.json'
        self.mapping = mmap.mmap(-1, ctypes.sizeof(IntroMusicShared), tagname=MAPPING_NAME)
        self.shared = IntroMusicShared.from_buffer(self.mapping)
        if self.shared.owner and self.shared.owner != os.getpid():
            import psutil
            if psutil.pid_exists(self.shared.owner):
                del self.shared
                self.mapping.close()
                raise RuntimeError('Outro Server controla a música de entrada')
        self.shared.version = 1
        self.shared.owner = os.getpid()
        self.shared.phase = 0
        self.shared.ack = self.shared.command
        self.shared.status = 0
        self.shared.error = 0
        self.game_pid = 0
        self.pending = False
        self._last_setting = None
        self._last_attempt = 0.0
        self._diagnostics = None
        self._diagnostics_logged_at = 0.0

    def tick(self, prematch: bool):
        self.shared.heartbeat = ctypes.windll.kernel32.GetTickCount() & 0xffffffff
        self.shared.phase = 1 if prematch else 2
        pid = self.app._resolve_fifa_pid() if self.app.memory.is_open() else 0
        if pid != self.game_pid:
            self.game_pid = pid
            self.pending = False
            self._last_setting = None
            self.shared.ack = self.shared.command
            self.shared.status = 0
            self.shared.error = 0

        if self.pending and self.shared.ack == self.shared.command:
            self.pending = False
            if self.shared.status == 2:
                self.app.log('Intro music: profile loaded in memory; audio switch awaits playback confirmation')
            else:
                self.app.log(f'Intro music profile rejected (error {self.shared.error})')

        diagnostics = (self.shared.ready, self.shared.status, self.shared.error,
                       self.shared.hook_calls, self.shared.description_reads,
                       self.shared.sbs_paths, self.shared.music_paths,
                       self.shared.reads, self.shared.replaced, self.shared.last_path)
        now = time.monotonic()
        if diagnostics != self._diagnostics and now - self._diagnostics_logged_at >= 2.0:
            self._diagnostics = diagnostics
            self._diagnostics_logged_at = now
            self.app.log('Intro music trace: ready={} status={} error={} calls={} descriptions={} sbs_paths={} intro_paths={} reads={} replaced={} last_path={!r}'.format(*diagnostics))

        configuration = _settings(self.settings_path)
        enabled = configuration.get('enabled', False) is True
        profile_name = str(configuration.get('default_profile', '')).strip()
        package = (self.root / profile_name / 'profile.npack').resolve() if enabled and profile_name else None
        if package is not None and package.parent.parent != self.root.resolve():
            package = None
        value = str(package) if package is not None and package.is_file() else ''

        if not self.shared.ready or not prematch or self.pending:
            return
        if value == self._last_setting:
            return
        # Avoid retry loops when a profile is absent or was rejected. A new
        # settings value or a new game session permits another attempt.
        if time.monotonic() - self._last_attempt < 2.0:
            return
        if value and len(value) >= 1024:
            self.app.log('Intro music profile path exceeds the native limit')
            self._last_setting = value
            return
        self.shared.package = value
        self.shared.status = 0
        self.shared.error = 0
        self.shared.command = (self.shared.command + 1) & 0xffffffff
        self.pending = True
        self._last_setting = value
        self._last_attempt = time.monotonic()
        self.app.log('Intro music: loading external profile' if value else 'Intro music: external profile disabled')

    def close(self):
        self.shared.owner = 0
        del self.shared
        self.mapping.close()


def intro_music_runtime(app):
    runtime = getattr(app, '_intro_music_runtime', None)
    if runtime is None:
        runtime = IntroMusicRuntime(app)
        app._intro_music_runtime = runtime
    return runtime
