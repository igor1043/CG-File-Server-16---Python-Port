"""Prepare scene assets in the preview; never fire effects or change options."""
from __future__ import annotations
import configparser
import json
import queue
import struct
import threading
import time
import xml.etree.ElementTree as E
from pathlib import Path
from types import SimpleNamespace

from .entrance_props_runtime import EntrancePropsRuntime
from .match_presentation import MatchPresentation
from .presentation_bridge import PresentationBridge, NAMES
from .stadium_catalog import prematch_page

LABELS = ('Entradas', 'Pirotecnia', 'VAR', 'Máquinas de fumaça')


def warm_file(path, cancelled, *, rx3=False):
    """Validate and read through the file into the OS cache on a worker."""
    path = Path(path)
    size = path.stat().st_size
    if size < 16 or size > 32*1024*1024:
        raise ValueError(f'Invalid resource size: {path}')
    with path.open('rb') as handle:
        header = handle.read(16)
        if rx3 and (header[:4] != b'RX3l' or struct.unpack_from('<I', header, 8)[0] != size):
            raise ValueError(f'Invalid RX3 header: {path}')
        while not cancelled.is_set() and handle.read(1024*1024):
            pass
    if cancelled.is_set():
        raise InterruptedError('Fixture preparation cancelled')


def enabled_modules(root):
    try:
        return {line.strip().replace('\\', '/').split('/')[0].casefold()
                for line in (root/'ModCarrerMode/mods/enabled.txt').read_text(encoding='utf-8-sig').splitlines()
                if line.strip() and not line.lstrip().startswith('#')}
    except OSError:
        return set()


def module_enabled(root, name):
    parser = configparser.ConfigParser(interpolation=None)
    path = root/'ModCarrerMode/mods'/name
    parser.read(path/('pyro.ini' if name == 'stadium_pyrotechnics' else name+'.ini'), encoding='utf-8-sig')
    return parser.getboolean('pyro' if name == 'stadium_pyrotechnics' else name, 'enabled', fallback=True)


def prepare_assets(snapshot, cancelled, report):
    root = Path(snapshot.exedir)
    options = MatchPresentation(root).load()
    installed = enabled_modules(root)
    for index, name in enumerate(NAMES):
        if cancelled.is_set():
            return
        try:
            active = name in installed and module_enabled(root, name)
            if name == 'entrance_props':
                active = active and options.entrance_props
            if name == 'stadium_pyrotechnics':
                active = active and options.pyrotechnics and (options.entrance or options.goal)
            if name == 'smoke_machine':
                active = active and options.pyrotechnics and (options.entrance or options.goal) and 'stadium_pyrotechnics' in installed
            if not active:
                report(index, 'skipped', 'Desativado')
                continue
            report(index, 'loading', 'Preparando arquivos')
            dll = root/f'ModCarrerMode/mods/{name}/{name}.dll'
            if not dll.is_file():
                raise FileNotFoundError(dll)
            if name == 'entrance_props':
                runtime = EntrancePropsRuntime(snapshot)
                directory = runtime.prepare_match(valid=lambda: not cancelled.is_set())
                if cancelled.is_set():
                    return
                if directory is None:
                    status = runtime._last_selection[6] if runtime._last_selection else 'unavailable'
                    pending = status == 'friendly_database_pending'
                    invalid = any(word in status for word in ('missing', 'invalid', 'unsupported'))
                    report(index, 'error' if invalid else 'pending' if pending else 'skipped',
                           'Entrada ausente ou inválida' if invalid else 'Aguardando banco de times' if pending else 'Sem entrada atribuída')
                    continue
                paths = [(directory/'model.rx3', True), (directory/'template.rx3', True)]
            elif name == 'stadium_pyrotechnics':
                directory = root/'data/sceneassets/particles'
                lnx = directory/'stadium_pyrotechnics_0.lnx'
                warm_file(lnx, cancelled)
                tree = E.parse(lnx)
                groups = tree.findall('.//particleGroup')
                if len(groups) != 11:
                    raise ValueError('Incomplete pyrotechnic particle resource')
                for group in groups:
                    emitter = next((a for a in group.findall('particleAction') if a.get('className') in ('ParticleActionEmitBox', 'ParticleActionEmitSphere')), None)
                    flag = emitter.find("parameter[@name='bRespectExternalTrigger']") if emitter is not None else None
                    if flag is None or flag.get('value') != '1':
                        raise ValueError('Particle resource cannot restart after home goals')
                paths = [(directory/'stadium_pyrotechnics_0.rx3', True)]
            else:
                directory = root/'data/sceneassets'/name
                paths = [(directory/'model.rx3', True), (directory/'textures.rx3', True)]
            for path, rx3 in paths:
                warm_file(path, cancelled, rx3=rx3)
            report(index, 'prepared', 'Arquivos preparados')
        except InterruptedError:
            return
        except FileNotFoundError as exc:
            snapshot.log(f'Presentation preload missing: {exc}')
            report(index, 'error', 'Arquivo ausente')
        except (OSError, ValueError, E.ParseError, configparser.Error) as exc:
            snapshot.log(f'Presentation preload invalid: {name}: {exc}')
            report(index, 'error', 'Recurso inválido')


class PresentationLoading:
    def __init__(self, app, *, bridge=None):
        self.app = app
        self.bridge = bridge if bridge is not None else PresentationBridge()
        self.key = None
        self.generation = 0
        self.cancelled = threading.Event()
        self.events = queue.Queue()
        self.rows = [('pending', 'Aguardando preparação')]*4
        self.next_tick = self.next_stamp = 0.0
        self.stamp = ()
        self.notice = None
        self.visible = False
        self.completed = False
        self.thread = None

    def _snapshot(self, pid):
        app = self.app
        return SimpleNamespace(exedir=Path(app.exedir), HID=str(app.HID), AID=str(app.AID),
            TOURNAME=str(app.TOURNAME or ''), TOURROUNDID=str(app.TOURROUNDID or ''),
            lastpagename=app.lastpagename, team_db=getattr(app, 'team_db', None),
            memory=SimpleNamespace(process_id=pid), log=app.log)

    def _configuration_stamp(self, root):
        names = ['ModCarrerMode/mods/enabled.txt', 'ModCarrerMode/config/match_presentation.ini', 'FSW/settings.ini']
        for name in NAMES:
            names.extend([f'ModCarrerMode/mods/{name}/{name}.dll',
                          f'ModCarrerMode/mods/{name}/'+('pyro.ini' if name == 'stadium_pyrotechnics' else name+'.ini')])
        result = []
        for name in names:
            try:
                st = (root/name).stat()
                result.append((st.st_mtime_ns, st.st_size))
            except OSError:
                result.append(None)
        return tuple(result)

    def tick(self):
        app = self.app
        preview = app.memory.is_open() and prematch_page(app.lastpagename)
        if not preview:
            if self.key is not None:
                self.cancelled.set()
                self.generation += 1
                self.key = None
                self.notice = None
                if self.visible:
                    app._finish_asset_loading('presentation')
                self.visible = False
                self.bridge.close()
            return  # No configuration reads, files, thread or native polls in gameplay.
        now = time.monotonic()
        if now < self.next_tick:
            return
        self.next_tick = now+.25
        pid = int(getattr(app.memory, 'process_id', 0) or app._resolve_fifa_pid() or 0)
        if not pid or not str(app.HID).isdigit() or not str(app.AID).isdigit() or int(app.HID)<=0 or int(app.AID)<=0:
            return
        root = Path(app.exedir)
        if now >= self.next_stamp:
            self.stamp = self._configuration_stamp(root)
            self.next_stamp = now+1
        key = (str(root), pid, app._kickoff_generation, str(app.HID), str(app.AID),
               str(app.TOURNAME), str(app.TOURROUNDID), str(app.STADID), getattr(app, 'curstad', ''),
               id(getattr(app, 'team_db', None)), self.stamp)
        if key != self.key:
            self.cancelled.set()
            self.cancelled = threading.Event()
            self.generation += 1
            self.key = key
            self.rows = [('pending', 'Aguardando preparação')]*4
            self.completed = False
            snapshot, cancelled, generation = self._snapshot(pid), self.cancelled, self.generation
            def run():
                try:
                    prepare_assets(snapshot, cancelled, lambda i, state, text: self.events.put((generation, i, state, text)))
                except Exception as exc:
                    snapshot.log('Presentation preparation failed', exc)
                    for i in range(4):
                        self.events.put((generation, i, 'error', 'Falha na preparação'))
            self.thread = threading.Thread(target=run, name='match-presentation-preload', daemon=True)
            self.thread.start()
            app.log(f'Presentation preload started: pid={pid} home={app.HID} away={app.AID} stadium={app.STADID}')
        while True:
            try:
                generation, index, state, text = self.events.get_nowait()
            except queue.Empty:
                break
            if generation == self.generation:
                self.rows[index] = state, text
        native = self.bridge.read(pid)
        lines, units, terminal, errors = [], 0, True, False
        for i, (state, text) in enumerate(self.rows):
            if state == 'prepared':
                status = native.get(NAMES[i], 0)
                text = {0:'Aguardando módulo', 1:'Aguardando cena 3D', 2:'Carregando cena 3D',
                        3:'Pronto na cena 3D', 4:'Sem uso nesta partida', 5:'Falha na cena 3D'}[status]
                units += 2 if status in (3, 4, 5) else 1
                terminal = terminal and status in (3, 4, 5)
                errors = errors or status == 5
            elif state in ('skipped', 'error'):
                units += 2
                errors = errors or state == 'error'
            else:
                terminal = False
            lines.append(f'{LABELS[i]}: {text}')
        title = 'Recursos com pendências' if terminal and errors else 'Recursos preparados' if terminal else 'Carregando apresentação'
        detail = '\n'.join(lines)
        notice = (title, detail, units*12.5)
        if self.completed and not terminal:
            self.visible = False
            self.completed = False
            self.notice = None
        injector = getattr(app, '_d3d_injector', None)
        move_to_native = bool(self.visible and injector is not None and injector.is_injected() and not getattr(app, '_presentation_native', False))
        if notice != self.notice or move_to_native:
            if not self.visible or title != (self.notice or ('',))[0] or move_to_native:
                app._show_asset_loading('presentation', title, title, detail, units*12.5)
                self.visible = True
            else:
                app._update_asset_loading('presentation', units*12.5, detail)
            self.notice = notice
            app.log('Presentation preload: '+detail.replace('\n', '; '))
            if terminal:
                app._hide_asset_loading('presentation', delay_ms=4000 if errors else 1800)
        if terminal and not self.completed:
            self.completed = True
            payload = dict(process_id=pid, home=app.HID, away=app.AID, stadium=app.STADID,
                           resources=dict(zip(NAMES, lines)), prepared=not errors)
            try:
                EntrancePropsRuntime._publish(root/'runtime/presentation_loading.json', json.dumps(payload, ensure_ascii=False, indent=2))
            except OSError as exc:
                app.log('Presentation diagnostic could not be saved', exc)

    def close(self):
        self.cancelled.set()
        self.bridge.close()

