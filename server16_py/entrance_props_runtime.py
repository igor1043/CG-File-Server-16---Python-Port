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


COMPETITION_SECTIONS = ('movies', 'Scoreboard', 'comp')


def competition_id(value: str) -> bool:
    return bool(re.fullmatch(r'[1-9][0-9]{0,5}', value or ''))


def resolve_asset(game_root: Path, competition: str, round_id: str = '', *, settings=None) -> tuple[Path | None, str]:
    """Use only IDs configured in the original Server16 settings file.

    A configured round with its own asset.ini overrides the main competition.
    Empty round folders inherit the main competition; invalid explicit packages
    are rejected rather than silently loading a different ceremony.
    """
    root = Path(game_root)
    path = root / 'FSW/settings.ini'
    if not path.is_file():
        return None, 'settings_missing'
    try:
        settings = settings if settings is not None else SessionIniFile(path)
        directory = None
        configured = False
        for key in dict.fromkeys((round_id, competition)):
            if not competition_id(key) or not any(settings.key_exists(key, section) for section in COMPETITION_SECTIONS):
                continue
            configured = True
            candidate = root / 'data/sceneassets/entrance_props/competitions' / key
            if (candidate / 'asset.ini').is_file():
                directory = candidate
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

    def prepare_match(self):
        app = self.app
        root = Path(app.exedir)
        competition, round_id = str(app.TOURNAME or ''), str(app.TOURROUNDID or '')
        try:
            enabled = MatchPresentation(root).load().entrance_props
            directory, status = resolve_asset(root, competition, round_id, settings=getattr(app, 'settings_ini', None)) if enabled else (None, 'disabled')
            selected = directory.name if directory else ''
            selection = (app.HID, app.AID, competition, round_id, enabled, selected, status)
            if selection != self._last_selection:
                app.log(f'Entrance props: competition={competition} round={round_id} asset={selected or "-"} status={status}')
                self._last_selection = selection
            # Diagnostic only: the DLL uses the same settings.ini IDs and the
            # live fixture, then validates RX3 buffers before loading.
            destination = root / 'runtime/entrance_props_selection.json'
            destination.parent.mkdir(parents=True, exist_ok=True)
            payload = dict(home=app.HID, away=app.AID, competition=competition, round=round_id,
                           enabled=enabled, asset=selected, status=status, source='FSW/settings.ini')
            fd, temporary = tempfile.mkstemp(prefix='entrance_selection_', suffix='.tmp', dir=destination.parent)
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                    json.dump(payload, handle, ensure_ascii=False, indent=2)
                os.replace(temporary, destination)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            return directory
        except Exception as exc:
            app.log('Entrance props skipped; other match assets continue', exc)
            return None
