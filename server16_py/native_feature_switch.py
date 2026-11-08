"""Small persistent switches for native features owned by the shared mod host."""
from pathlib import Path
import os
import re
from threading import Lock

_ultrawide_lock = Lock()

class NativeFeatureSwitch:
    feature = ''
    module = ''
    def __init__(self, game_directory):
        self.mods = Path(game_directory) / 'ModCarrerMode' / 'mods'
        self.ini = self.mods / self.feature / (self.feature + '.ini')
    def available(self):
        return self.ini.is_file() and (self.mods / self.module).is_file()
    def enabled(self):
        try:
            text = self.ini.read_text(encoding='utf-8-sig')
            section = re.search(r'(?mis)^\s*\[' + re.escape(self.feature) + r'\]\s*\n(.*?)(?=^\s*\[|\Z)', text)
            value = re.search(r'(?mi)^\s*enabled\s*=\s*([01])\s*(?:[;#].*)?$', section[1]) if section else None
            return bool(self.available() and value and value[1] == '1')
        except (OSError, UnicodeError):
            return False
    def set_enabled(self, enabled):
        if not self.available():
            raise FileNotFoundError('O recurso não está instalado nesta pasta do FIFA.')
        data = self.ini.read_bytes()
        text = data.decode('utf-8-sig')
        section = re.search(r'(?mis)(^\s*\[' + re.escape(self.feature) + r'\][^\r\n]*\r?\n)(.*?)(?=^\s*\[|\Z)', text)
        if not section:
            raise ValueError('Configuração do recurso não encontrada.')
        body = section[2]
        pattern = r'(?mi)^([ \t]*enabled[ \t]*=[ \t]*)[01]([^\r\n]*)'
        if not re.search(pattern, body):
            raise ValueError('Configuração enabled não encontrada.')
        body = re.sub(pattern, lambda m: m[1] + str(int(bool(enabled))) + m[2], body)
        output = (text[:section.start(2)] + body + text[section.end(2):]).encode('utf-8')
        if data.startswith(b'\xef\xbb\xbf'):output = b'\xef\xbb\xbf' + output
        temporary = self.ini.with_name(self.ini.name + f'.{os.getpid()}.tmp')
        try:
            temporary.write_bytes(output)
            os.replace(temporary, self.ini)
        finally:
            if temporary.exists():temporary.unlink()

class UltrawideSwitch(NativeFeatureSwitch):
    feature = 'ultrawide'
    module = 'server16_overlay/cgfs16_overlay.dll'

    def sync_background(self):
        from .ultrawide_background import apply_background
        with _ultrawide_lock:
            return apply_background(self.mods.parent.parent, self.enabled())

    def set_enabled(self, enabled):
        from .ultrawide_background import apply_background
        setter = super().set_enabled
        with _ultrawide_lock:
            apply_background(self.mods.parent.parent, enabled, commit=lambda: setter(enabled))

class LowDrivenShotSwitch(NativeFeatureSwitch):
    feature = 'low_driven_shot'
    module = 'low_driven_shot/low_driven_shot.dll'
