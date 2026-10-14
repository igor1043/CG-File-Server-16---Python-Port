from __future__ import annotations

import configparser
import io
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PresentationOptions:
    mascots: bool = True
    pyrotechnics: bool = False
    entrance: bool = False
    goal: bool = False
    entrance_props: bool = True


class MatchPresentation:
    """Only the dedicated mod configuration is edited; no FIFA assets or loader."""
    KEYS = ('mascots', 'pyrotechnics', 'entrance', 'goal', 'entrance_props')

    def __init__(self, game_root):
        self.path = Path(game_root) / 'ModCarrerMode' / 'config' / 'match_presentation.ini'

    def _read(self):
        parser = configparser.ConfigParser(interpolation=None)
        if self.path.exists():
            parser.read_string(self.path.read_text(encoding='utf-8-sig'))
        return parser

    def load(self):
        parser = self._read()
        defaults = PresentationOptions()
        return PresentationOptions(**{key: parser.getboolean('match', key, fallback=getattr(defaults, key))
                                       for key in self.KEYS})

    def save(self, options):
        parser = self._read()  # Malformed files must not be silently overwritten.
        if not parser.has_section('match'):
            parser.add_section('match')
        for key in self.KEYS:
            parser.set('match', key, '1' if getattr(options, key) else '0')
        parser.set('match', 'schema', '1')
        stream = io.StringIO()
        parser.write(stream)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='match_presentation_', suffix='.tmp', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as handle:
                handle.write(stream.getvalue())
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
