from __future__ import annotations

import ctypes
import mmap
import os
import queue
import threading
import time
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .stadium_catalog import COUNTRIES, COUNTRY_FLAGS, build_catalog, filter_catalog, normalize, prematch_page
from .file_tools import STADIUM_ARCHIVE_SUFFIXES
from .overlay_canvas import OverlayDraw, FOCUSED_PRIMARY, draw_focus_ring
from .input_hints import panel_function_key
from .match_audio_panel import MatchAudioPanel
from .match_state import pause_page
from .crowd_control import CrowdControl
from .prematch_panel import PrematchPanel
from .narration_runtime import narration_runtime
from .intro_music_runtime import intro_music_runtime
from .match_hub_panel import MatchHubPanel
from .career_service import CareerService, career_page, safe_exit_page
from .career_panel import CareerPanel

SELECTOR_MAPPING_NAME = 'Local\\CGFS16_Selector_v1'

class SelectorEvent(ctypes.Structure):
    _fields_ = [('kind',ctypes.c_int32),('value',ctypes.c_int32)]

class SelectorShared(ctypes.Structure):
    _fields_ = [
        ('owner_pid',ctypes.c_uint32),('heartbeat',ctypes.c_uint32),
        ('enabled',ctypes.c_int32),('visible',ctypes.c_int32),('ready',ctypes.c_int32),
        ('render_ready',ctypes.c_int32),('width',ctypes.c_int32),('height',ctypes.c_int32),
        ('read_index',ctypes.c_int32),('write_index',ctypes.c_int32),
        ('events',SelectorEvent*64),('image_path',ctypes.c_wchar*512),
    ]

class StadiumSelector:
    WIDTH = 600
    HEIGHT = 600
    KEYBOARD_WIDTH = 1000
    KEYBOARD_HEIGHT = 830
    PHOTO_RECT = (24,130,576,362)
    KEYS = list('QWERTYUIOPASDFGHJKLZXCVBNM0123456789') + ['Espaço','Apagar','Limpar','Buscar']

    def __init__(self, app):
        self.app = app
        self.entries = []
        self.results = []
        self.query = self.draft = self.country = ''
        self.index = self.focus = self.key_index = 0
        self.keyboard = self.opened = False
        self.applying = False
        self.audio_panel = None
        self.career_panel = None
        self.career_service = CareerService(app)
        self._career_notice_shown = False
        self.prematch_panel = None
        self.controller_connected = False
        self.return_to_menu = False
        self.crowd_control = None
        self._match_context = None
        self._catalog_key = None
        self._catalog_ready = False
        self._catalog_pending_key = None
        self._catalog_cache = []
        self._opening_selection_names = ()
        self._next_preload = 0.0
        self._crests = OrderedDict()
        self.context = None
        self.message = ''
        self.targets = []
        self.serial = 0
        self.loading = False
        self._catalog_results = queue.Queue()
        self._catalog_generation = 0
        self._catalog_thread = None
        self._image_jobs = queue.Queue(maxsize=1)
        self._image_results = queue.Queue()
        self._image_stop = threading.Event()
        self._image_thread = None
        self._image_generation = 0
        self._preview_selection = None
        self._preview_image = None
        self._preview_loading = False
        self._preview_cache = OrderedDict()
        self._preview_transition = False
        self._next_loader = 0.0
        self._flags = {}
        self.cache = app.base_dir / 'runtime' / 'stadium_selector'
        self.cache.mkdir(parents=True,exist_ok=True)
        self.mapping = mmap.mmap(-1,ctypes.sizeof(SelectorShared),tagname=SELECTOR_MAPPING_NAME)
        self.shared = SelectorShared.from_buffer(self.mapping)
        previous_owner = self.shared.owner_pid
        if previous_owner and previous_owner != os.getpid():
            kernel = ctypes.windll.kernel32
            kernel.OpenProcess.restype = ctypes.c_void_p
            kernel.CloseHandle.argtypes = [ctypes.c_void_p]
            process = kernel.OpenProcess(0x100000, False, previous_owner)
            if process:
                kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
                running = kernel.WaitForSingleObject(process, 0) == 258
                kernel.CloseHandle(process)
                if running:
                    self.shared = None
                    self.mapping.close()
                    raise RuntimeError('Stadium selector is already owned by another server instance')
        self.shared.owner_pid = os.getpid()
        self.shared.visible = self.shared.enabled = self.shared.render_ready = 0
        self.shared.read_index = self.shared.write_index = 0
        self.crowd_control = CrowdControl(app)
        self._attempted_pid = 0
        self._next_injection = 0.0
        self._status = None
        app.log('Overlay channel initialized: stadium F12 / Start; match settings F12 / Select+Start')

    def match_eligible(self):
        app = self.app
        page = (app.lastpagename or '').lower()
        # The clock/start memory signal is independent of whether Chants is enabled.
        allowed=('ingame', 'pause', 'replay', 'fluxhub', 'stadiumpan')
        if getattr(app, '_match_audio_ended', False) or not app.memory.is_open() or prematch_page(app.lastpagename) or 'training' in page or 'skillgame' in page:
            self._match_context=None
            return False
        if page and not pause_page(page) and not any(token in page for token in allowed):
            self._match_context=None
            return False
        checker = getattr(app, '_is_game_running_with', None)
        if callable(checker) and checker(app.memory):
            self._match_context=self._context()
            return True
        return bool(self._match_context==self._context() and (not page or pause_page(page) or any(token in page for token in allowed)))

    def tick(self):
        app = self.app
        self.career_service.tick()
        camera=getattr(app,'_first_person_runtime',None)
        if camera is not None:camera.tick()
        if time.monotonic() >= getattr(self,'_next_cloth_sync',0):
            from .cloth_motion_switch import ClothMotionSwitch
            switch=ClothMotionSwitch(getattr(app,'exedir',app.base_dir))
            enabled=switch.enabled()
            var=getattr(app,'module_vars',{}).get('ClothPhysics')
            if var is not None and var.get()!=enabled:var.set(enabled)
            getattr(app,'module_states',{})['ClothPhysics']=enabled
            self._next_cloth_sync=time.monotonic()+1
        shared = self.shared
        shared.heartbeat = ctypes.windll.kernel32.GetTickCount()
        prematch_eligible = app.memory.is_open() and prematch_page(app.lastpagename)
        runtime=getattr(app,'_narration_runtime',None)
        game_root=Path(getattr(app,'exedir',app.base_dir))
        if runtime is not None or (game_root/'Narrations').is_dir() or (game_root/'IntroMusic').is_dir():
            narration_runtime(app).tick(prematch_eligible)
        music_runtime=getattr(app,'_intro_music_runtime',None)
        if music_runtime is not None or (game_root/'IntroMusic').is_dir():
            intro_music_runtime(app).tick(prematch_eligible)
        stadium_eligible = prematch_eligible and app.module_enabled('Stadium')
        career_eligible = app.memory.is_open() and (self.career_service.in_career(app.lastpagename) or
            ((self.career_service.pending or self.career_service.notice_available()) and
             (safe_exit_page(app.lastpagename) or self.career_service.context_reader.exited_hub(app.lastpagename))))
        mode = 1 if prematch_eligible else 3 if career_eligible else 2 if self.match_eligible() else 0
        page=(app.lastpagename or '').lower()
        # Keep attendance through walkout/loading, pause and gameplay, but not
        # Career menus or post-match pages. Editing is still pre-match only.
        crowd_phase = bool(not getattr(app, '_match_audio_ended', False) and
            (mode==2 or 'tv/bumper' in page or
             (not page and (getattr(app, '_stadium_fixture_entered', False) or
                            self.crowd_control.shared.requested_percent>=0)) or
             ('stadiumpan' in page and self.crowd_control.shared.requested_percent>=0)))
        self.crowd_control.tick(prematch_eligible,crowd_phase)
        opened_mode = 3 if self.career_panel else 2 if self.audio_panel else 1
        if self.opened and (not mode or opened_mode != mode or
                            (mode != 3 and self.context != self._context())):
            self.close()
        if stadium_eligible and time.monotonic() >= self._next_preload:
            self._preload_catalog()
            self._next_preload = time.monotonic()+5.0
        self._drain_catalog()
        self._drain_images()
        if self.opened and self.prematch_panel:
            self.prematch_panel.tick()
        if self.opened and self.audio_panel:
            self.audio_panel.tick()
        if self.opened and self.career_panel:
            self.career_panel.tick()
        if self.opened and not self.audio_panel and not self.prematch_panel and (self._preview_loading or self.loading) and time.monotonic()>=self._next_loader:
            self.render()
        if self.applying and not app._stadium_task_running:
            self.applying=False
            if self.opened and not self.prematch_panel and not self.audio_panel:
                self.back()
        shared.enabled = mode if not app._overlay_visible else 0
        if mode:
            pid = app._resolve_fifa_pid()
            if pid and pid != self._attempted_pid and time.monotonic() >= self._next_injection:
                shared.ready = 0
                if app._ensure_d3d_overlay_injected():
                    self._attempted_pid = pid
                self._next_injection = time.monotonic() + 5.0
                shared.heartbeat = ctypes.windll.kernel32.GetTickCount()
        status = (app.lastpagename, mode, shared.enabled, shared.ready)
        if status != self._status:
            self._status = status
            app.log(f'Overlay status: page={app.lastpagename!r} mode={mode} enabled={shared.enabled} native_ready={shared.ready}/7')
        if self.opened and not shared.visible:
            self.close()
        while shared.read_index != shared.write_index:
            event = shared.events[shared.read_index]
            kind,value = event.kind,event.value
            shared.read_index=(shared.read_index+1)%64
            if kind==1:
                if shared.enabled and shared.ready==7:
                    self.open(audio=shared.enabled==2,hub=shared.enabled==1,career=shared.enabled==3)
                else:
                    app.log(f'Stadium selector shortcut rejected: enabled={shared.enabled} native_ready={shared.ready}/7')
                    self.close()
            elif kind==17 or self.opened:
                self.handle(kind,value)

    def _context(self):
        app=self.app
        return (app._kickoff_generation,app.HID,app.AID,app.TOURNAME,app.TOURROUNDID)

    def _preload_catalog(self):
        teams=dict(getattr(self.app.team_db,'team_cache',{}))
        assignments=tuple(self.app.settings_ini.items('stadium')) if self.app.settings_ini is not None else ()
        settings=SimpleNamespace(items=lambda section:assignments)
        root=self.app.targetpath
        if not root:
            return
        root=Path(root)
        try: stamp=root.stat().st_mtime_ns
        except OSError: stamp=0
        key=(str(root),stamp,assignments,tuple(teams.items()))
        if key==self._catalog_key or key==self._catalog_pending_key:
            return
        self._catalog_pending_key=key
        self._catalog_generation+=1
        generation=self._catalog_generation
        def load():
            try:
                entries=build_catalog(root,settings,teams)
                self._catalog_results.put((generation,key,entries,None))
            except Exception as exc:
                self._catalog_results.put((generation,key,[],exc))
        self._catalog_thread=threading.Thread(target=load,name='stadium-catalog',daemon=True)
        self._catalog_thread.start()

    def open(self, audio=False, hub=False, career=False):
        self.context=self._context()
        self.applying=False
        self.audio_panel=MatchHubPanel(self) if audio else None
        self.career_panel=CareerPanel(self,self.career_service) if career else None
        self.prematch_panel=None
        self.return_to_menu=False
        self.country=self.query=self.draft=self.message=''
        self.index=0; self.focus=2; self.keyboard=False
        self.opened=True
        if career:
            self._opening_selection_names=()
            self.loading=False
            self.render()
            return
        if hub and not audio:
            self.show_menu()
            return
        if audio:
            self._opening_selection_names=()
            self.loading=False
            self.render()
            return
        self._preload_catalog()
        self.entries=list(self._catalog_cache)
        self.loading=not self._catalog_ready
        self._opening_selection_names=self._preferred_stadium_names()
        self.refresh(preferred_names=self._opening_selection_names)
        if self._catalog_pending_key is None:
            self._opening_selection_names=()
        selected=self.results[self.index].name if self.results else ''
        self.app.log(f'Stadium selector opened: selected={selected!r} loading={self.loading}')

    def show_menu(self):
        self.keyboard=False
        self.loading=False
        self.audio_panel=None
        self.career_panel=None
        self.prematch_panel=PrematchPanel(self)
        self.return_to_menu=True
        self.render()

    def back(self):
        if self.return_to_menu:
            self.show_menu()
        else:
            self.close()

    def keep_crowd_on_setup_return(self, previous_page):
        app=self.app
        context=self._context()
        return (self.crowd_control.context==(context[0],CrowdControl.team_id(context[1]),CrowdControl.team_id(context[2])) and
                self.crowd_control.shared.requested_percent>=0 and
                not getattr(app,'_stadium_fixture_entered',False) and
                not getattr(app,'_match_audio_ended',False) and
                (not previous_page or prematch_page(previous_page) or 'stadiumpan' in previous_page.lower()))

    def _preferred_stadium_names(self):
        app=self.app
        names=[]
        pending=getattr(app.stadium_runtime,'pending_selection',None)
        if getattr(app,'_stadium_task_running',False) and pending and pending[0]==self.context[:3]:
            names.append(pending[1])
        manual=getattr(app,'_manual_stadium_override',None)
        if manual and manual[0]==self.context:
            names.append(manual[1])
        names.extend((getattr(app,'curstad',''),getattr(app,'StadName','')))
        return tuple(dict.fromkeys(name for name in names if name))

    @staticmethod
    def _stadium_key(name):
        name=Path(name.strip()).name
        if Path(name).suffix.lower() in STADIUM_ARCHIVE_SUFFIXES:
            name=Path(name).stem
        return normalize(name)

    def _drain_catalog(self):
        while True:
            try: generation,key,entries,error=self._catalog_results.get_nowait()
            except queue.Empty: return
            if generation!=self._catalog_generation:
                continue
            self._catalog_pending_key=None
            if error:
                self.app.log('Stadium selector catalog failed',error)
            else:
                self._catalog_key=key
                self._catalog_ready=True
                self._catalog_cache=entries
                self.app.log(f'Stadium selector catalog ready: {len(entries)} installed packages')
            if self.opened and not self.audio_panel and not self.prematch_panel:
                selected=self.results[self.index].name if self.results else ''
                preferred=self._opening_selection_names or ((selected,) if selected else ())
                self.loading=False
                self.entries=entries
                if error: self.message='Não foi possível carregar a lista de estádios'
                self.refresh(preferred_names=preferred)
                self._opening_selection_names=()
            elif entries:
                self._request_preview(entries[0])

    def close(self):
        self._opening_selection_names=()
        self._image_generation+=1
        self._preview_selection=None
        self._preview_image=None
        self._preview_loading=False
        self._preview_transition=False
        self.shared.visible=self.shared.render_ready=0
        self.opened=self.loading=False; self.keyboard=False
        self.applying=False
        self.audio_panel=None
        self.career_panel=None
        self.prematch_panel=None
        self.return_to_menu=False

    def shutdown(self):
        self.career_service.feedback.close()
        self._image_stop.set()
        self.career_service.jobs_runtime.close()
        self.close(); self.shared.enabled=0; self.shared.owner_pid=0
        self.crowd_control.shutdown()
        runtime=getattr(self.app,'_narration_runtime',None)
        if runtime is not None:
            runtime.close();self.app._narration_runtime=None
        music_runtime=getattr(self.app,'_intro_music_runtime',None)
        if music_runtime is not None:
            music_runtime.close();self.app._intro_music_runtime=None
        camera=getattr(self.app,'_first_person_runtime',None)
        if camera is not None:
            camera.close();self.app._first_person_runtime=None
        self.shared=None
        self.mapping.close()

    def refresh(self,preferred_names=()):
        self.results=filter_catalog(self.entries,self.query,self.country)
        for name in preferred_names:
            key=self._stadium_key(name)
            match=next((i for i,entry in enumerate(self.results) if self._stadium_key(entry.name)==key),None)
            if match is not None:
                self.index=match
                break
        self.index=min(self.index,max(0,len(self.results)-1))
        self.render()

    def apply(self):
        if not self.results or self.context!=self._context() or not prematch_page(self.app.lastpagename):
            self.message='Seleção indisponível nesta tela'; self.render(); return
        entry=self.results[self.index]
        try:
            self.app.stadium_runtime.apply_manual_stadium(entry.name,self.context)
        except Exception as exc:
            self.message='Não foi possível aplicar o estádio'
            self.app.log('Manual stadium selection failed',exc)
            self.render()
            return
        # The stadium runtime now owns the screen and reports real copy
        # progress through the existing D3D/Tk loading notice. The shortcut
        # remains enabled, so the selector can be reopened while it loads.
        self.back()

    def search(self):
        self._opening_selection_names=()
        self.query=self.draft[:80]; self.keyboard=False; self.index=0; self.focus=2
        self.refresh()

    def key(self, label):
        if label=='Buscar': self.search(); return
        if label=='Limpar': self.draft=''
        elif label=='Apagar': self.draft=self.draft[:-1]
        elif label=='Espaço': self.draft=(self.draft+' ')[:80]
        else: self.draft=(self.draft+label)[:80]
        self.render()

    def action(self, action):
        self._opening_selection_names=()
        if action=='search': self.keyboard=True; self.key_index=0; self.focus=0; self.render()
        elif action=='apply': self.apply()
        elif action=='cancel': self.back()
        elif action in ('prev','next'): self.change(1 if action=='next' else -1,2)
        elif action in ('country_prev','country_next'): self.change(1 if action=='country_next' else -1,1)
        elif action.startswith('country:'):
            self.country=action[8:]; self.index=0; self.focus=1; self.refresh()
        elif action.startswith('key:'): self.key(action[4:])

    def change(self,direction,focus):
        self._opening_selection_names=()
        self.focus=focus
        if focus==1:
            countries=['']+sorted({e.country for e in self.entries},key=lambda c:COUNTRIES.get(c,c))
            self.country=countries[(countries.index(self.country)+direction)%len(countries)]
            self.index=0; self.refresh()
        elif focus==2 and self.results:
            self.index=(self.index+direction)%len(self.results); self.render()
        elif focus>=3:
            self.focus=4 if direction<0 else 3; self.render()

    def hover(self, x, y):
        # Motion only changes focus; it never searches, applies or types.
        action=next((action for rect,action in self.targets
                     if rect[0]<=x<=rect[2] and rect[1]<=y<=rect[3]),None)
        if self.keyboard:
            if action and action.startswith('key:'):
                index=self.KEYS.index(action[4:])
                if index!=self.key_index:
                    self.key_index=index; self.render()
            return
        if action in ('prev','next') or (self.PHOTO_RECT[0]<=x<=self.PHOTO_RECT[2] and
                                       self.PHOTO_RECT[1]<=y<=self.PHOTO_RECT[3]): focus=2
        elif action=='search': focus=0
        elif action and action.startswith('country'): focus=1
        elif action=='apply': focus=3
        elif action=='cancel': focus=4
        else: return
        if focus!=self.focus:
            self.focus=focus; self.render()

    def handle(self,kind,value):
        if kind==17:
            connected=bool(value)
            if connected!=self.controller_connected:
                self.controller_connected=connected
                if self.opened:
                    self.render()
            return
        if self.audio_panel:
            self.audio_panel.handle(kind,value)
            return
        if self.career_panel:
            self.career_panel.handle(kind,value)
            return
        if self.prematch_panel:
            self.prematch_panel.handle(kind,value)
            return
        # Browsing after Apply must not close the newly browsed selection when
        # the earlier asynchronous stadium job finishes.
        self.applying=False
        if kind==15: self.hover(value&65535,(value>>16)&65535)
        elif kind==11: self.close()
        elif kind in (13,14) and not self.keyboard:
            self.change(-1 if kind==13 else 1,1)
        elif kind==7:
            if self.keyboard: self.keyboard=False; self.focus=2; self.render()
            else: self.back()
        elif kind==16:
            if value==1:
                self.search() if self.keyboard else self.apply()
            elif value==2:
                if self.keyboard: self.keyboard=False; self.focus=2; self.render()
                else: self.back()
        elif kind==9: self.action('search')
        elif kind==8:
            x,y=value&65535,(value>>16)&65535
            for rect,action in self.targets:
                if rect[0]<=x<=rect[2] and rect[1]<=y<=rect[3]: self.action(action); break
        elif kind==10 and self.keyboard:
            self.key('Apagar' if value==8 else chr(value))
        elif self.keyboard:
            if kind==6: self.key(self.KEYS[self.key_index])
            else:
                if kind in (2,3):
                    self.key_index=(self.key_index+(1 if kind==3 else -1))%len(self.KEYS)
                elif kind==4:
                    if self.key_index>=36: self.key_index=24+(self.key_index-36)*12//4
                    elif self.key_index<12: self.key_index=36+self.key_index*4//12
                    else: self.key_index-=12
                elif kind==5:
                    if self.key_index>=36: self.key_index=(self.key_index-36)*12//4
                    elif self.key_index>=24: self.key_index=36+(self.key_index-24)*4//12
                    else: self.key_index+=12
                self.render()
        elif kind==6:
            self.action({0:'search',1:'country_next',2:'apply',3:'apply',4:'cancel'}[self.focus])
        elif kind in (4,5):
            vertical={0:(0,1),1:(0,2),2:(1,3),3:(2,3),4:(2,4)}
            self.focus=vertical[self.focus][kind==5]; self.render()
        elif kind in (2,3): self.change(1 if kind==3 else -1,self.focus)

    @staticmethod
    @lru_cache(maxsize=64)
    def font(size,bold=False):
        fonts=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'
        try: return ImageFont.truetype(str(fonts/('segoeuib.ttf' if bold else 'segoeui.ttf')),size*2)
        except OSError: return ImageFont.load_default()

    @staticmethod
    def stadium_title(entry):
        title=entry.title
        parts=title.rsplit(' - ',1)
        if len(parts)==2 and entry.team_id and entry.club:
            tail,club=normalize(parts[1]),normalize(entry.club)
            if tail==club or (len(tail)>=5 and f' {tail} ' in f' {club} '):
                return parts[0]
        return title

    @staticmethod
    def count_label(count):
        return f'{count:,}'.replace(',','.')

    def position_label(self):
        return f'{self.count_label(self.index+1 if self.results else 0)} de {self.count_label(len(self.results))}'

    def flag(self,country):
        if country in self._flags: return self._flags[country]
        code=COUNTRY_FLAGS.get(country)
        flag=None
        if code:
            path=Path(__file__).resolve().parent/'assets'/'flags'/f'{code}.png'
            try:
                with Image.open(path) as source: flag=ImageOps.contain(source.convert('RGBA'),(48,32))
            except (OSError,ValueError): pass
        self._flags[country]=flag
        return flag

    @staticmethod
    def _load_preview(path):
        with Image.open(path) as source:
            return ImageOps.fit(source.convert('RGB'),(1104,464),method=Image.Resampling.LANCZOS)

    def _preview_worker(self):
        while not self._image_stop.is_set():
            try: generation,path=self._image_jobs.get(timeout=0.25)
            except queue.Empty: continue
            try: preview=self._load_preview(path); error=None
            except Exception as exc: preview=None; error=exc
            self._image_results.put((generation,path,preview,error))

    def _request_preview(self,entry):
        selection=(entry.name,str(entry.preview or '')) if entry else None
        if selection==self._preview_selection:
            return
        self._preview_selection=selection
        self._image_generation+=1
        if not entry or not entry.preview:
            self._preview_image=None; self._preview_loading=False
            return
        path=str(entry.preview)
        if path in self._preview_cache:
            self._preview_image=self._preview_cache[path]
            self._preview_cache.move_to_end(path)
            self._preview_loading=False; self._preview_transition=True
            return
        self._preview_loading=True
        if self._image_thread is None:
            self._image_thread=threading.Thread(target=self._preview_worker,name='stadium-photo',daemon=True)
            self._image_thread.start()
        # Keep only the most recent pending photo when navigation is rapid.
        try: self._image_jobs.get_nowait()
        except queue.Empty: pass
        self._image_jobs.put_nowait((self._image_generation,path))

    def _drain_images(self):
        while True:
            try: generation,path,preview,error=self._image_results.get_nowait()
            except queue.Empty: return
            if preview is not None:
                self._preview_cache[path]=preview
                self._preview_cache.move_to_end(path)
                while len(self._preview_cache)>12: self._preview_cache.popitem(last=False)
            elif error:
                self.app.log(f'Stadium selector preview unavailable: {path}',error)
            if generation==self._image_generation:
                self._preview_loading=False
                self._preview_image=preview
                self._preview_transition=preview is not None
                if self.opened and not self.audio_panel: self.render()

    def _publish(self, image, width, height):
        self.serial+=1
        prefix='card_slide' if self._preview_transition and not self.audio_panel else 'card'
        output=self.cache/f'{prefix}_{self.serial%2}.png'
        temporary=output.with_suffix('.tmp')
        image.save(temporary,format='PNG',compress_level=1); temporary.replace(output)
        # Keep the published frame available during PIL drawing/encoding.
        # Only metadata publication uses a short seqlock; native retains the
        # previous texture while this revision is negative.
        self.shared.render_ready=-self.serial
        self.shared.width=width; self.shared.height=height
        self.shared.image_path=str(output)
        self.shared.render_ready=self.serial; self.shared.visible=1
        self._preview_transition=False

    def render(self):
        if self.career_panel:
            self._publish(self.career_panel.render(), self.career_panel.WIDTH, self.career_panel.HEIGHT)
            return
        if self.audio_panel:
            self._publish(self.audio_panel.render(), self.audio_panel.WIDTH, self.audio_panel.HEIGHT)
            return
        if self.prematch_panel:
            self._publish(self.prematch_panel.render(), self.prematch_panel.WIDTH, self.prematch_panel.HEIGHT)
            return
        height=self.KEYBOARD_HEIGHT if self.keyboard else self.HEIGHT
        image=Image.new('RGBA',(self.WIDTH*2,self.HEIGHT*2),(0,0,0,0))
        draw=OverlayDraw(image); self.targets=[]
        ink,muted,blue='#344651','#8797ab','#0968f8'
        draw.rounded_rectangle((0,0,self.WIDTH-1,self.HEIGHT-1),18,fill='#ffffff',outline='#e0e6ee')
        def text(x,y,value,size=17,color=ink,bold=False,max_width=552):
            font=self.font(size,bold)
            if draw.textlength(value,font=font)>max_width:
                while value and draw.textlength(value+'…',font=font)>max_width: value=value[:-1]
                value+='…'
            draw.text((x,y),value,font=font,fill=color)
        def button(rect,label,action,selected=False,primary=False):
            fill=FOCUSED_PRIMARY if primary and selected else blue if primary else '#eef4ff' if selected else '#ffffff'
            draw.rounded_rectangle(rect,10,fill=fill,outline=blue if selected else blue if primary else '#c9d3df',width=2 if selected else 1)
            if selected:
                draw_focus_ring(draw,rect)
            font=self.font(17)
            tw=draw.textlength(label,font=font)
            th=font.getbbox(label)[3]/2
            icon_offset=12 if action in ('cancel','apply') else 0
            draw.text(((rect[0]+rect[2]-tw)/2+icon_offset,(rect[1]+rect[3]-th)/2-1),label,font=font,fill='#ffffff' if primary else ink)
            icon_x=rect[0]+78; icon_y=(rect[1]+rect[3])//2
            if action=='apply':
                draw.line(((icon_x-5,icon_y),(icon_x,icon_y+5),(icon_x+10,icon_y-7)),fill='#ffffff',width=2)
            elif action=='cancel':
                draw.line(((icon_x-5,icon_y-5),(icon_x+5,icon_y+5)),fill=muted,width=2)
                draw.line(((icon_x-5,icon_y+5),(icon_x+5,icon_y-5)),fill=muted,width=2)
            self.targets.append((rect,action))
        def chevron(cx,cy,direction,color=ink,width=3):
            draw.line([(cx-direction*3,cy-7),(cx+direction*4,cy),(cx-direction*3,cy+7)],fill=color,width=width)
        def stadium_icon(cx,cy):
            draw.ellipse((cx-25,cy-12,cx+25,cy+8),outline='#596c79',width=3)
            draw.arc((cx-25,cy-4,cx+25,cy+17),0,180,fill='#596c79',width=3)
            draw.ellipse((cx-17,cy-7,cx+17,cy+3),outline='#596c79',width=2)
            for offset in (-19,-10,0,10,19):
                draw.line((cx+offset,cy+7,cx+offset,cy+13),fill='#596c79',width=2)
            draw.line((cx-7,cy-18,cx+7,cy-18),fill='#596c79',width=2)
        search_rect=(24,22,576,72)
        draw.rounded_rectangle(search_rect,12,fill='#eef2f7',outline=blue if self.focus==0 else '#eef2f7',width=2)
        if self.focus==0 and not self.keyboard: draw_focus_ring(draw,search_rect,12)
        draw.ellipse((41,36,55,50),outline='#738499',width=2)
        draw.line((53,48,60,55),fill='#738499',width=2)
        text(76,35,self.draft or 'Buscar estádio...',18,color=ink if self.draft else muted,max_width=404)
        text(510,39,'Y / Tab',13,color=muted,max_width=56)
        self.targets.append((search_rect,'search'))
        countries=['']+sorted({entry.country for entry in self.entries},key=lambda code:COUNTRIES.get(code,code))
        current=countries.index(self.country) if self.country in countries else 0
        start=max(0,min(current-1,len(countries)-4))
        chevron(34,101,-1,color=muted,width=2); chevron(333,101,1,color=muted,width=2)
        self.targets.extend([((24,82,46,122),'country_prev'),((323,82,344,122),'country_next')])
        for i,country in enumerate(countries[start:start+4]):
            x=51+i*67; rect=(x,82,x+60,122); selected=country==self.country
            draw.rounded_rectangle(rect,8,fill='#eef4ff' if selected else '#f4f7fb',outline=blue if selected and self.focus==1 else '#d8e5f6' if selected else '#eaf0f6')
            if selected and self.focus==1 and not self.keyboard: draw_focus_ring(draw,rect,8)
            flag=self.flag(country)
            if flag:
                image.alpha_composite(flag,(x*2+(120-flag.width)//2,172+(32-flag.height)//2))
                text(x+18,103,country,10,color=ink,max_width=38)
            else: text(x+9,92,'Todos' if not country else country,13,color=ink,max_width=45)
            self.targets.append((rect,'country:'+country))
        count=self.count_label(len(self.results))
        total=self.count_label(len(self.entries))
        filtered=bool(self.query or self.country)
        counter=f'{count} filtrados · {total} no total' if filtered else f'{total} estádios no total'
        counter_size=12 if filtered else 14
        text(576-draw.textlength(counter,font=self.font(counter_size)),87,counter,counter_size,color=muted,max_width=232)
        entry=self.results[self.index] if self.results else None
        self._request_preview(entry)
        photo_rect=self.PHOTO_RECT
        draw.rounded_rectangle(photo_rect,14,fill='#edf2f7')
        preview_ok=False
        if self._preview_image is not None:
            preview=self._preview_image
            mask=Image.new('L',preview.size,0)
            ImageDraw.Draw(mask).rounded_rectangle((0,0,preview.width-1,preview.height-1),28,fill=255)
            image.paste(preview,(48,260),mask)
            preview_ok=True
        if not preview_ok:
            stadium_icon(300,220)
            label='Carregando estádios...' if self.loading else '' if self._preview_loading else 'Sem imagem de prévia' if entry else 'Nenhum estádio encontrado'
            font=self.font(20)
            text((self.WIDTH-draw.textlength(label,font=font))/2,263,label,20,color=muted)
        if self._preview_loading:
            draw.rounded_rectangle((183,272,417,314),12,fill='#ffffff',outline='#e0e7ef')
            angle=int(time.monotonic()*300)%360
            draw.arc((198,283,218,303),angle,angle+260,fill=blue,width=3)
            text(230,282,'Carregando imagem...',14,color=muted,max_width=180)
            self._next_loader=time.monotonic()+0.12
        if self.loading:
            draw.rounded_rectangle((170,300,430,307),4,fill='#dfe9f7')
            phase=(time.monotonic()%1.8)/1.8
            phase=phase*2 if phase<.5 else (1-phase)*2
            left=170+180*phase
            draw.rounded_rectangle((left,300,left+80,307),4,fill=blue)
            self._next_loader=time.monotonic()+0.12
        draw.rounded_rectangle(photo_rect,14,outline=blue if self.focus==2 else '#e4eaf1',width=2 if self.focus==2 else 1)
        if self.focus==2 and not self.keyboard: draw_focus_ring(draw,photo_rect,14)
        for cx,action,direction in ((52,'prev',-1),(548,'next',1)):
            rect=(cx-20,226,cx+20,266)
            draw.ellipse(rect,fill='#ffffff',outline='#dce4ec')
            chevron(cx,246,direction)
            self.targets.append((rect,action))
        stadium_icon(51,402)
        if entry:
            text(96,385,self.stadium_title(entry),22,bold=True,max_width=370)
            if entry.team_id:
                crest=self.app._resolve_team_logo_path(entry.team_id)
                if crest:
                    try:
                        if crest not in self._crests:
                            with Image.open(crest) as source: self._crests[crest]=ImageOps.contain(source.convert('RGBA'),(124,124))
                            while len(self._crests)>32: self._crests.popitem(last=False)
                        logo=self._crests[crest]
                        self._crests.move_to_end(crest)
                        draw.line((486,380,486,427),fill='#e0e7ef',width=1)
                        image.alpha_composite(logo,(1004+(124-logo.width)//2,744+(124-logo.height)//2))
                    except (OSError,ValueError): pass
            text(576-draw.textlength(self.position_label(),font=self.font(13)),438,self.position_label(),13,color=muted,max_width=150)
        else:
            text(96,390,'Selecione um estádio',21,color=muted,max_width=370)
            text(576-draw.textlength(self.position_label(),font=self.font(13)),438,self.position_label(),13,color=muted,max_width=150)
        draw.line((1,467,598,467),fill='#e9eef4',width=1)
        button((24,481,292,529),f'Voltar · {panel_function_key(2)} / B' if self.return_to_menu else f'Cancelar · {panel_function_key(2)} / B','cancel',self.focus==4)
        button((308,481,576,529),f'Aplicar · {panel_function_key(1)}','apply',self.focus==3,primary=True)
        if self.message:
            text(24,554,self.message,13,color='#8c5b24',max_width=552)
        else:
            hint={0:'Busca selecionada · A / Enter Digitar',1:'País selecionado · ← → Trocar país',
                  2:'Estádio selecionado · ← → Trocar · A / Enter Aplicar',
                  3:'Aplicar selecionado · A / Enter Confirmar',4:'Cancelar selecionado · A / Enter Fechar'}[self.focus]
            text(24,554,hint,12,color=ink,max_width=552)
        if self.keyboard:
            # A single transport texture, but two separate screen panels.
            # Native rendering places the card at the top and keyboard below.
            combined=Image.new('RGBA',(self.KEYBOARD_WIDTH*2,height*2),(0,0,0,0))
            combined.alpha_composite(image,(self.KEYBOARD_WIDTH-self.WIDTH,0))
            image=combined; draw=OverlayDraw(image)
            draw.rounded_rectangle((0,self.HEIGHT,self.KEYBOARD_WIDTH-1,height-1),16,fill='#ffffff',outline='#dce5ee')
            text(20,self.HEIGHT+14,'TECLADO',16,bold=True)
            text(165,self.HEIGHT+16,'Setas + A para digitar • Buscar confirma • B retorna ao estádio',14,color=muted,max_width=805)
            for i,key in enumerate(self.KEYS):
                # The final row reserves wider keys for the four actions.
                if i>=36:
                    x=20+(i-36)*240; y=self.HEIGHT+174
                    button((x,y,x+232,y+40),key,'key:'+key,i==self.key_index,primary=key=='Buscar')
                else:
                    x=20+(i%12)*80; y=self.HEIGHT+48+(i//12)*38
                    button((x,y,x+72,y+32),key,'key:'+key,i==self.key_index)
        self._publish(image,self.KEYBOARD_WIDTH if self.keyboard else self.WIDTH,height)
