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
    smoke_entrance_seconds: int = 60
    smoke_goal_seconds: int = 25
    smoke_entrance_emitters: int = (1 << 20)-1
    smoke_goal_emitters: int = (1 << 12)-1


class MatchPresentation:
    """Only the dedicated mod configuration is edited; no FIFA assets or loader."""
    KEYS = ('mascots', 'pyrotechnics', 'entrance', 'goal', 'entrance_props')
    NUMBERS = {'smoke_entrance_seconds': (15,120), 'smoke_goal_seconds': (15,120),
               'smoke_entrance_emitters': (0,(1<<20)-1), 'smoke_goal_emitters': (0,(1<<12)-1)}

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
        values={key:parser.getboolean('match',key,fallback=getattr(defaults,key)) for key in self.KEYS}
        values.update({key:parser.getint('match',key,fallback=getattr(defaults,key)) for key in self.NUMBERS})
        options=PresentationOptions(**values)
        self.validate(options)
        return options

    @classmethod
    def validate(cls,options):
        for key,(low,high) in cls.NUMBERS.items():
            value=getattr(options,key)
            if type(value) is not int or not low<=value<=high:
                raise ValueError('Valor inválido na configuração de fumaça: '+key)

    def save(self, options):
        self.validate(options)
        parser = self._read()  # Malformed files must not be silently overwritten.
        if not parser.has_section('match'):
            parser.add_section('match')
        for key in self.KEYS:
            parser.set('match', key, '1' if getattr(options, key) else '0')
        for key in self.NUMBERS:parser.set('match',key,str(getattr(options,key)))
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
