"""Select the optional ceremony using the same competition context as stadiums."""
from __future__ import annotations

import configparser
import hashlib
import json
import os
import re
import struct
import tempfile
from pathlib import Path

from .ini_file import SessionIniFile
from .match_presentation import MatchPresentation
from .entrance_friendly import common_league_competition, no_competition


COMPETITION_SECTIONS = ('movies', 'Scoreboard', 'comp')


def competition_id(value: str) -> bool:
    return bool(re.fullmatch(r'[1-9][0-9]{0,5}', value or ''))


def resolve_asset(game_root: Path, competition: str, round_id: str = '', *, settings=None) -> tuple[Path | None, str]:
    """Use only IDs configured in the original Server16 settings file.

    A configured round package has priority. When absent, use the configured
    main competition package, matching the working Robson 12.12 behavior.
    An explicitly present but corrupt package is rejected.
    """
    root = Path(game_root)
    path = root / 'FSW/settings.ini'
    if not path.is_file():
        return None, 'settings_missing'
    try:
        settings = settings if settings is not None else SessionIniFile(path)
        if not no_competition(round_id) and not competition_id(round_id):
            return None, 'competition_unconfigured'
        directory = None
        configured = False
        for candidate in dict.fromkeys((round_id, competition)):
            if not competition_id(candidate) or not any(settings.key_exists(candidate, section) for section in COMPETITION_SECTIONS):
                continue
            configured = True
            package = root / 'data/sceneassets/entrance_props/competitions' / candidate
            if (package / 'asset.ini').is_file():
                directory = package
                break
        if directory is None:
            return None, 'asset_missing' if configured else 'competition_unconfigured'
        metadata = configparser.ConfigParser(interpolation=None)
        metadata.read_string((directory / 'asset.ini').read_text(encoding='utf-8-sig'))
        if metadata.getint('asset', 'schema') != 1:
            return None, 'unsupported_asset_schema'
        for name, key, hash_key in (('model.rx3', 'model_bytes', 'model_sha256'), ('template.rx3', 'texture_bytes', 'texture_sha256')):
            file = directory / name
            expected = metadata.getint('asset', key)
            if expected < 32 or expected > 32 * 1024 * 1024 or file.stat().st_size != expected:
                return None, 'asset_size_invalid'
            with file.open('rb') as handle:
                header = handle.read(16)
                if len(header) != 16 or header[:4] != b'RX3l' or struct.unpack_from('<I', header, 8)[0] != expected:
                    return None, 'asset_header_invalid'
            expected_hash = metadata.get('asset', hash_key, fallback='')
            if not re.fullmatch('[a-fA-F0-9]{64}', expected_hash) or hashlib.sha256(file.read_bytes()).hexdigest() != expected_hash.lower():
                return None, 'asset_checksum_invalid'
        return directory, 'ready'
    except (OSError, ValueError, configparser.Error):
        return None, 'asset_missing_or_invalid'


class EntrancePropsRuntime:
    def __init__(self, app):
        self.app = app
        self._last_selection = None

    @staticmethod
    def _publish(destination: Path, payload: str):
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='entrance_selection_', suffix='.tmp', dir=destination.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                handle.write(payload)
            os.replace(temporary, destination)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def clear_context(self):
        """Invalidate a friendly selection as soon as a new fixture is entered."""
        self._last_selection = None
        try:
            self._publish(Path(self.app.exedir)/'runtime/entrance_props_context.ini', '[selection]\nschema=1\nmode=none\n')
        except OSError as exc:
            self.app.log('Entrance props context could not be cleared', exc)

    def prepare_match(self):
        app = self.app
        root = Path(app.exedir)
        competition, round_id = str(app.TOURNAME or ''), str(app.TOURROUNDID or '')
        try:
            enabled = MatchPresentation(root).load().entrance_props
            settings = getattr(app, 'settings_ini', None)
            resolved, league, mode = competition, '', 'competition'
            if enabled and no_competition(competition) and no_competition(round_id):
                resolved, league, mode = common_league_competition(root, str(app.HID or ''), str(app.AID or ''), getattr(app, 'team_db', None), settings)
                directory, status = resolve_asset(root, resolved, settings=settings) if resolved else (None, mode)
            else:
                directory, status = resolve_asset(root, competition, round_id, settings=settings) if enabled else (None, 'disabled')
            selected = directory.name if directory else ''
            selection = (app.HID, app.AID, competition, round_id, enabled, selected, status, resolved, mode, league)
            if selection != self._last_selection:
                app.log(f'Entrance props: competition={competition} round={round_id} asset={selected or "-"} status={status} mode={mode} league={league or "-"}')
                self._last_selection = selection
            # Friendly context is automatic Server16 IPC. The DLL checks the
            # current FIFA process, actual clubs, and settings.ini again.
            pid = int(getattr(getattr(app, 'memory', None), 'process_id', 0) or 0)
            context = dict(schema=1, process_id=pid, home=app.HID, away=app.AID,
                           competition=competition or '0', round=round_id or '0',
                           mode=mode if enabled and directory else 'none',
                           league=league or '0', asset=selected or '0', resolved_competition=resolved or '0')
            self._publish(root/'runtime/entrance_props_context.ini', '[selection]\n' + ''.join(f'{key}={value}\n' for key, value in context.items()))
            destination = root / 'runtime/entrance_props_selection.json'
            payload = dict(home=app.HID, away=app.AID, competition=competition, round=round_id,
                           enabled=enabled, asset=selected, status=status, source='FSW/settings.ini',
                           mode=mode, league=league, resolved_competition=resolved)
            self._publish(destination, json.dumps(payload, ensure_ascii=False, indent=2))
            return directory
        except Exception as exc:
            app.log('Entrance props skipped; other match assets continue', exc)
            return None
