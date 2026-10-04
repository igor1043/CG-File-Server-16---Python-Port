from __future__ import annotations

import copy
import json
import math
import os
import tempfile
from pathlib import Path


class AudioProfileError(ValueError):
    pass


def match_key(home, away):
    ids = [str(value or '').strip() for value in (home, away)]
    if not all(value.isascii() and value.isdigit() and int(value) > 0 for value in ids):
        return None
    return ':'.join(str(int(value)) for value in ids)


def _volume(value, maximum):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AudioProfileError('Volumes devem ser números.')
    if not 0 <= value <= maximum or not math.isfinite(value):
        raise AudioProfileError('Volume fora do intervalo permitido.')
    return float(value)


class AudioProfileStore:
    """Editable game-side profiles; malformed files are never replaced."""

    def __init__(self, path):
        self.path = Path(path)
        self.signature = None
        self.document = None

    def _stamp(self):
        try:
            info = self.path.stat()
            return info.st_mtime_ns, info.st_size, info.st_ino
        except FileNotFoundError:
            return None

    @staticmethod
    def _validate(document):
        if not isinstance(document, dict) or type(document.get('version')) is not int or document['version'] != 1:
            raise AudioProfileError('Formato ou versão de audio_profiles.json inválido.')
        matches = document.get('matches')
        if not isinstance(matches, dict):
            raise AudioProfileError('A seção matches deve ser um objeto.')
        for key, profile in matches.items():
            parts = key.split(':')
            if len(parts) != 2 or match_key(*parts) != key or not isinstance(profile, dict):
                raise AudioProfileError(f'Confronto inválido: {key}')
            _volume(profile.get('chants'), 2.0)
            _volume(profile.get('goal_hymns'), 1.0)
        return document

    def load(self, force=False):
        stamp = self._stamp()
        if stamp is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            try:
                # Exclusive creation preserves a file another instance just created.
                with self.path.open('x', encoding='utf-8') as handle:
                    json.dump({'version': 1, 'matches': {}}, handle, indent=2)
                    handle.flush()
                    os.fsync(handle.fileno())
            except FileExistsError:
                pass
            stamp = self._stamp()
        if force or self.document is None or stamp != self.signature:
            try:
                document = json.loads(self.path.read_text(encoding='utf-8-sig'))
                self.document = self._validate(document)
            except (ValueError, UnicodeError) as exc:
                self.document = None
                raise AudioProfileError(f'Arquivo de perfis inválido: {exc}') from exc
            self.signature = stamp
        return self.document

    def save_match(self, home, away, volumes=None):
        key = match_key(home, away)
        if key is None:
            raise AudioProfileError('IDs dos times ainda não estão disponíveis.')
        document = copy.deepcopy(self.load(force=True))
        original_stamp = self.signature
        if volumes is None:
            document['matches'].pop(key, None)
        else:
            crowd, goal = volumes
            profile = document['matches'].setdefault(key, {})
            profile.update(chants=_volume(crowd, 2.0), goal_hymns=_volume(goal, 1.0))
        self._validate(document)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                    prefix='.audio_profiles_', suffix='.tmp', dir=self.path.parent, delete=False) as handle:
                temporary = Path(handle.name)
                json.dump(document, handle, indent=2, ensure_ascii=False, allow_nan=False)
                handle.write('\n')
                handle.flush()
                os.fsync(handle.fileno())
            if self._stamp() != original_stamp:
                raise AudioProfileError('O arquivo mudou durante o salvamento. Tente novamente.')
            temporary.replace(self.path)
            self.document = document
            self.signature = self._stamp()
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


class AudioProfileRuntime:
    def __init__(self, app):
        self.app = app
        self.store = None
        self.source = 'general'
        self.has_match_profile = False
        self.error = ''
        self._last_error = ''
        self._state = None
        self._general_override = None

    @property
    def path(self):
        return self.store.path if self.store is not None else None

    def bind(self, game_root):
        path = Path(game_root) / 'FSW' / 'audio_profiles.json' if game_root is not None else None
        if path != self.path:
            self.store = AudioProfileStore(path) if path is not None else None
            self._state = None
            self._general_override = None

    def general_volumes(self):
        app = self.app
        settings = getattr(app, 'settings', None)
        values = (settings.crowd_master_volume, settings.goal_master_volume) if settings is not None else (
            getattr(app, '_crowd_master_volume', 1.0), getattr(app, '_goal_master_volume', 1.0))
        return tuple(max(0.0, min(maximum, float(value))) if math.isfinite(float(value)) else 1.0
                     for value, maximum in zip(values, (2.0, 1.0)))

    def sync(self, force=False, *, apply_general=False, refresh_live=False):
        app = self.app
        general = self.general_volumes()
        key = match_key(getattr(app, 'HID', ''), getattr(app, 'AID', ''))
        profile = None
        self.error = ''
        if self.store is not None:
            try:
                document = self.store.load(force=force)
                profile = document['matches'].get(key)
            except (OSError, ValueError) as exc:
                self.error = str(exc)
        if self.error and self.error != self._last_error:
            app.log(f'Audio profiles unavailable; file={self.path}; using general volumes: {self.error}')
        self._last_error = self.error
        self.has_match_profile = profile is not None
        profile_volumes = (float(profile['chants']), float(profile['goal_hymns'])) if profile is not None else None
        context = (self.path, getattr(app, '_kickoff_generation', 0), key)
        # An explicit general Apply also affects this fixture, without deleting
        # its saved profile. The next fixture/restart recovers match priority.
        override = (context, profile_volumes, general)
        if apply_general:
            self._general_override = override if self.has_match_profile else None
        if self.error or self._general_override != override:
            self._general_override = None
        self.source = 'match' if self.has_match_profile else 'general'
        volumes = profile_volumes if profile_volumes is not None else general
        if self._general_override is not None:
            self.source, volumes = 'general', general
        state = (*context, self.source, volumes, general)
        if force or state != self._state:
            changed = volumes != (getattr(app, '_crowd_master_volume', 1.0), getattr(app, '_goal_master_volume', 1.0))
            app._crowd_master_volume, app._goal_master_volume = volumes
            if (changed or refresh_live) and getattr(app, 'chants_runtime', None) is not None:
                app.chants_runtime.apply_crowd_master_volume()
                app.chants_runtime.apply_goal_master_volume()
            if state != self._state:
                app.log(f'Audio volume profile: {self.source}; match={key or "unknown"}; crowd={volumes[0]:.3f}; goal={volumes[1]:.3f}')
            self._state = state
        return volumes

    def save_general(self, volumes, *, apply_now=False):
        crowd, goal = volumes
        settings = self.app.settings
        previous = dict(settings.data)
        try:
            settings.data.update(CROWD_MASTER_VOLUME=_volume(crowd, 2.0), GOAL_MASTER_VOLUME=_volume(goal, 1.0))
            settings.save()
        except Exception:
            settings.data.clear()
            settings.data.update(previous)
            raise
        self.app._crowd_master_volume_dirty = False
        return self.sync(force=True, apply_general=apply_now, refresh_live=apply_now)

    def save_match(self, volumes=None, *, apply_now=False):
        if self.store is None:
            raise AudioProfileError('Selecione a instalação do FIFA primeiro.')
        self.store.save_match(self.app.HID, self.app.AID, volumes)
        self._general_override = None
        return self.sync(force=True, refresh_live=apply_now)

    def apply_general(self, volumes):
        return self.save_general(volumes, apply_now=True)

    def apply_match(self, volumes):
        return self.save_match(volumes, apply_now=True)


def audio_profiles(app):
    runtime = getattr(app, 'audio_profiles', None)
    if runtime is None:
        runtime = AudioProfileRuntime(app)
        app.audio_profiles = runtime
        runtime.bind(getattr(app, 'exedir', None))
    return runtime
