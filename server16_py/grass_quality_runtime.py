"""Optional grass detail override for the verified FIFA 16 render object.

Only mutable grass parameters are written. No executable instructions, shader
code, assets, save files or replay/gameplay state are changed.
"""
from __future__ import annotations
import configparser
import ctypes
import math
import os
import struct
import time
from pathlib import Path
from .match_state import read_native_match_scene, outside_match_page

GRASS_RENDER = 0x35047B0
GRASS_VTABLE = 0x220C758
BUILD_TIMESTAMP = 0x577DE45C


class GrassQualitySettings:
    def __init__(self, game):
        self.path = Path(game)/'ModCarrerMode/config/grass_quality.ini'

    def _read(self):
        doc = configparser.ConfigParser(interpolation=None)
        try:
            if self.path.exists():doc.read_string(self.path.read_text(encoding='utf-8-sig'))
        except configparser.Error as error:raise ValueError('Configuração do gramado inválida.') from error
        return doc

    def enabled(self):
        return self._read().getboolean('grass', 'high_quality', fallback=False)

    def set_enabled(self, enabled):
        if type(enabled) is not bool:raise ValueError('Opção de gramado inválida.')
        doc = self._read()
        if not doc.has_section('grass'):doc.add_section('grass')
        doc.set('grass', 'high_quality', str(int(enabled)))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name+f'.{os.getpid()}.new')
        try:
            with temporary.open('w', encoding='utf-8') as stream:doc.write(stream)
            os.replace(temporary, self.path)
        finally:temporary.unlink(missing_ok=True)


def detail_ranges(values):
    """Promote near detail inside the stadium's existing far drawing range."""
    if len(values)!=5 or not all(math.isfinite(v) for v in values):raise ValueError('Faixas do gramado inválidas.')
    if not 0<=values[0]<=values[1]<=values[2]<=values[3]<=values[4]<=20000 or values[2]<=0:
        raise ValueError('Faixas do gramado incompatíveis.')
    high = max(values[0], min(400., values[2]*.6))
    medium = max(values[1], high, min(700., values[2]*.85))
    return high, medium, *values[2:]


class GrassQualityRuntime:
    def __init__(self, app):
        self.app = app
        self.store = GrassQualitySettings(getattr(app, 'exedir', app.base_dir))
        self.error = ''
        try:self.enabled = self.store.enabled()
        except (OSError, ValueError) as error:self.enabled=False;self.error=str(error)
        self.active = False
        self.identity = None
        self.originals = {}
        self.written = {}
        self.pid = 0
        self.checked = None
        self.next_tick = self.next_settings = 0.
        self.lock = None
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
        self.kernel.CreateMutexW.restype = ctypes.c_void_p
        self.kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        self.lock = self.kernel.CreateMutexW(None, False, 'Local\\Server16_GrassQualityController_v1')
        self.controller = bool(self.lock) and ctypes.get_last_error()!=183
        if not self.controller and self.lock:self.kernel.CloseHandle(self.lock);self.lock=None

    def set_enabled(self, enabled):
        self.store.set_enabled(enabled)
        self.enabled = enabled
        self.next_tick = self.next_settings = 0.
        self.tick()

    def _scope(self, memory):
        base = memory.base_module
        renderer = memory.read_int64(base+GRASS_RENDER)
        owner = memory.read_int64(renderer+0x1B0)
        if memory.read_int64(renderer+0x500)!=owner or memory.read_int64(owner)!=base+GRASS_VTABLE:
            raise ValueError('Aguardando o gramado desta partida.')
        raw = memory.read_process_memory(owner, 0x6A8)
        width, length = struct.unpack_from('<2i', raw, 0x4C8)
        index = struct.unpack_from('<i', raw, 0x4B0)[0]
        params = struct.unpack_from('<Q', raw, 0x668)[0]
        if not 1000<=width<=20000 or not 1000<=length<=25000 or index!=1 or raw[0x5E4]!=1:
            raise ValueError('Aguardando o gramado principal da partida.')
        if params<0x10000 or params==owner or params==renderer:raise ValueError('Parâmetros do gramado indisponíveis.')
        detail_ranges(struct.unpack('<5f', memory.read_process_memory(params+0x24, 20)))
        return memory.process_id, base, renderer, owner, params, width, length

    def _same(self, memory):
        try:return self.identity is not None and self._scope(memory)==self.identity
        except (OSError, RuntimeError, ValueError, struct.error):return False

    def _write(self, memory, address, data):
        # Heap data is already writable. Do not call VirtualProtectEx or alter
        # permissions, and refuse a stale scene immediately before each write.
        if not self._same(memory):raise ValueError('O gramado mudou durante o ajuste.')
        buffer = ctypes.create_string_buffer(data)
        count = ctypes.c_size_t()
        ok = memory.kernel32.WriteProcessMemory(memory.process_handle, ctypes.c_void_p(address),
            buffer, len(data), ctypes.byref(count))
        if not ok or count.value!=len(data):raise OSError('Não foi possível ajustar o gramado.')

    def _restore(self, memory):
        if self._same(memory):
            for address, original in self.originals.items():
                # Preserve a later update made by FIFA or another controller.
                if memory.read_process_memory(address, len(original))==self.written.get(address):
                    self._write(memory, address, original)
        self.identity = None
        self.originals.clear();self.written.clear();self.active=False

    def _apply(self, memory):
        scope = self._scope(memory)
        if scope!=self.identity:
            self._restore(memory)
            self.identity=scope
        _, _, renderer, owner, params, _, _ = scope
        locations = ((owner+0x214, 8, 'fade'), (renderer+0x94, 8, 'fade'),
                     (params+0x24, 20, 'detail'), (renderer+0xA0, 20, 'detail'))
        for address, size, kind in locations:
            current = memory.read_process_memory(address, size)
            if address not in self.originals or current!=self.written.get(address):self.originals[address]=current
            original = self.originals[address]
            if kind=='detail':target=struct.pack('<5f', *detail_ranges(struct.unpack('<5f', original)))
            else:
                lower, upper = struct.unpack('<2f', original)
                if not math.isfinite(lower) or not math.isfinite(upper) or not 0<=lower<upper<=50000:
                    raise ValueError('Distância de exibição do gramado incompatível.')
                target=struct.pack('<2f', max(lower, 8000.), max(upper, 12000.))
            if current!=target:self._write(memory, address, target)
            self.written[address]=target
        self.active=True

    def tick(self):
        now=time.monotonic()
        if now<self.next_tick:return
        self.next_tick=now+.1
        memory=self.app.memory
        try:
            if now>=self.next_settings:
                self.enabled=self.store.enabled();self.next_settings=now+.5
            if not self.controller:
                self.error='Outro Server16 controla o gramado.';return
            if not self.enabled and not self.identity:
                self.active=False;self.error='';return
            if not memory.is_open():
                self.identity=None;self.originals.clear();self.written.clear();self.active=False;return
            if memory.process_id!=self.pid:
                self.identity=None;self.originals.clear();self.written.clear();self.active=False
                self.pid=memory.process_id;self.checked=None
            if not self.enabled:
                self._restore(memory);self.error='';return
            if self.checked!=(memory.process_id,memory.base_module):
                base=memory.base_module;pe=memory.read_uint32(base+0x3C)
                if (memory.read_process_memory(base,2)!=b'MZ' or not 0x40<=pe<0x1000
                    or memory.read_process_memory(base+pe,4)!=b'PE\0\0'
                    or memory.read_uint32(base+pe+8)!=BUILD_TIMESTAMP):
                    raise ValueError('Versão do FIFA incompatível com o ajuste de gramado.')
                self.checked=(memory.process_id,memory.base_module)
            scene=read_native_match_scene(memory)
            page=getattr(self.app,'lastpagename','')
            # Phase 1 also occurs while an already loaded match is paused.
            # The exact grass owner/index, dimensions and build guards below
            # still have to validate before touching that stadium's parameters.
            if not scene or not 1<=scene.phase<=15 or outside_match_page(page) or 'career/' in page.casefold():
                self._restore(memory);self.error='';return
            self._apply(memory);self.error=''
        except (OSError, RuntimeError, ValueError, configparser.Error, struct.error) as error:
            try:self._restore(memory)
            except (OSError, RuntimeError, ValueError, struct.error):self.active=False
            message=str(error)
            if message!=self.error:self.app.log('Grass quality waiting: '+message)
            self.error=message

    def status(self):
        if self.error:return self.error
        if not self.enabled:return 'Desligado · detalhe original do estádio'
        return 'Ligado · grama 3D em jogo' if self.active else 'Ligado · aguardando partida'

    def close(self):
        try:self._restore(self.app.memory)
        except (OSError, RuntimeError, ValueError, struct.error):pass
        finally:
            if self.lock:self.kernel.CloseHandle(self.lock);self.lock=None
            self.controller=False


def grass_quality_runtime(app):
    runtime=getattr(app,'_grass_quality_runtime',None)
    if runtime is None:
        runtime=GrassQualityRuntime(app);app._grass_quality_runtime=runtime
    return runtime
