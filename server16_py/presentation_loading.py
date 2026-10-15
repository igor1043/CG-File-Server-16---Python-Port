"""Prepare scene assets silently in the preview; retain background diagnostics."""
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
from .match_state import pause_page

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
        self.completed = False
        self.thread = None
        self.tracking = False
        self.track_deadline = 0.0

    def _stop(self):
        self.cancelled.set()
        self.generation += 1
        self.key = None
        self.tracking = False
        self.track_deadline = 0.0
        self.notice = None
        self.bridge.close()

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
            if self.key is None:
                return  # Settled gameplay: no files, workers or native polling.
            page = (app.lastpagename or '').casefold()
            loading = not page or page in ('tv/bumper', 'game/screens/tv/bumper') or 'loading' in page or 'ingame' in page or pause_page(page)
            pid = int(getattr(app.memory, 'process_id', 0) or 0)
            changed_clubs = any(str(getattr(app, field, '') or '') not in ('', self.key[index])
                                for field, index in (('HID', 3), ('AID', 4)))
            if not app.memory.is_open() or pid != self.key[1] or changed_clubs or not loading or getattr(app, '_match_audio_ended', False):
                self._stop()
                return
            now = time.monotonic()
            if not self.tracking:
                self.cancelled.set()
                self.generation += 1
                self.tracking = True
                self.track_deadline = now+15
                self.notice = None
                self.completed = False
                self.next_tick = 0
            if now < self.next_tick:
                return
            self.next_tick = now+.5
            native = self.bridge.read(pid)
            done = self._render(native, starting=True, timed_out=now >= self.track_deadline)
            if done:
                self._stop()
            return
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
            self.tracking = False
            self.track_deadline = 0.0
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
        self._render(self.bridge.read(pid))

    def _render(self, native, *, starting=False, timed_out=False):
        app = self.app
        lines, units, terminal, errors = [], 0, True, False
        for i, (state, text) in enumerate(self.rows):
            if state == 'prepared' or (starting and state in ('pending', 'loading')):
                status = native.get(NAMES[i], 0)
                if starting:
                    text = {0:'Aguardando confirmação do jogo', 1:'Aguardando cena 3D', 2:'Carregando cena 3D',
                            3:'Pronto no jogo', 4:'Sem uso nesta partida', 5:'Falha na cena 3D'}[status]
                    if timed_out and status in (0, 1, 2):
                        text = 'Sem confirmação da cena'
                    units += 2 if status in (3, 4, 5) else 1
                    terminal = terminal and status in (3, 4, 5)
                else:
                    text = {0:'Preparado para iniciar', 1:'Preparado para iniciar', 2:'Preparado; carregando cena',
                            3:'Pronto na cena 3D', 4:'Sem uso nesta partida', 5:'Falha na cena 3D'}[status]
                    units += 2  # Preview progress measures file preparation.
                errors = errors or status == 5
            elif state in ('skipped', 'error'):
                units += 2
                errors = errors or state == 'error'
            else:
                terminal = False
            lines.append(f'{LABELS[i]}: {text}')
        done = terminal or timed_out
        title = ('Confirmação incompleta' if timed_out and not terminal else
                 'Recursos com pendências' if terminal and errors else
                 'Apresentação carregada' if starting and terminal else
                 'Pré-jogo preparado' if terminal else
                 'Carregando cena da partida' if starting else 'Preparando apresentação')
        detail = '\n'.join(lines)
        notice = (title, detail, units*12.5)
        if self.completed and not terminal:
            self.completed = False
            self.notice = None
        # Keep preload and bounded scene acknowledgements active without
        # showing a D3D card, a fallback window, or scheduling hide timers.
        if notice != self.notice:
            self.notice = notice
            app.log('Presentation preload: '+detail.replace('\n', '; '))
        if done and not self.completed:
            self.completed = True
            payload = dict(process_id=self.key[1], home=app.HID, away=app.AID, stadium=app.STADID,
                           phase='match_loading' if starting else 'preview',
                           resources=dict(zip(NAMES, lines)), native_states=native,
                           files_prepared=all(state in ('prepared', 'skipped') for state, text in self.rows),
                           scene_confirmed=starting and terminal and not errors)
            try:
                EntrancePropsRuntime._publish(Path(app.exedir)/'runtime/presentation_loading.json', json.dumps(payload, ensure_ascii=False, indent=2))
            except OSError as exc:
                app.log('Presentation diagnostic could not be saved', exc)
        return done

    def close(self):
        self.cancelled.set()
        self.bridge.close()

