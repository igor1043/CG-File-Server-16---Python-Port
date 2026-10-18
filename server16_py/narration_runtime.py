"""Narration DLL channel, acknowledged profile changes and pre-match gating."""
from __future__ import annotations
import ctypes, mmap, os, json, subprocess, time, threading, queue
from pathlib import Path
from .narration_competitions import choose_profile
from .narration_paths import narration_root, profile_directories
MAPPING_NAME='Local\\FIFA16_Narration_v1'

def load_preferences(path):
    try:return json.loads(Path(path).read_text(encoding='utf8'))
    except (OSError,ValueError):return {}

def save_preferences(path,name):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    data=load_preferences(path);data.update(version=1,default_narrator=name)
    temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8');temporary.replace(path)

def narration_dll_loaded(pid, dll_name='fifa16_narration.dll'):
    """Reuse the game worker when the Server is reopened in the same session."""
    from ctypes import wintypes as w
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    psapi=ctypes.WinDLL('psapi',use_last_error=True)
    kernel.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];kernel.OpenProcess.restype=w.HANDLE
    kernel.CloseHandle.argtypes=[w.HANDLE]
    psapi.EnumProcessModulesEx.argtypes=[w.HANDLE,ctypes.POINTER(w.HMODULE),w.DWORD,ctypes.POINTER(w.DWORD),w.DWORD]
    psapi.GetModuleBaseNameW.argtypes=[w.HANDLE,w.HMODULE,w.LPWSTR,w.DWORD]
    handle=kernel.OpenProcess(0x410,False,pid)
    if not handle:return False
    try:
        modules=(w.HMODULE*2048)();needed=w.DWORD()
        if not psapi.EnumProcessModulesEx(handle,modules,ctypes.sizeof(modules),ctypes.byref(needed),3):return False
        for module in modules[:min(2048,needed.value//ctypes.sizeof(w.HMODULE))]:
            name=ctypes.create_unicode_buffer(260)
            if psapi.GetModuleBaseNameW(handle,module,name,len(name)) and name.value.lower()==dll_name.lower():return True
        return False
    finally:kernel.CloseHandle(handle)

class NarrationShared(ctypes.Structure):
    _fields_=[(name,ctypes.c_uint32) for name in ('version','owner','heartbeat','command','ack','ready','phase','status','error','reads','replaced','cache_count','cache_writes','unsupported')]+[('package',ctypes.c_wchar*1024)]

class NarrationRuntime:
    def __init__(self,app):
        self.app=app;self.root=narration_root(getattr(app,'exedir',app.base_dir))
        self.preferences_path=self.root.parent/'FSW/narration_settings.json'
        self.default_narrator=load_preferences(self.preferences_path).get('default_narrator','Tiago Leifert')
        self.mapping=mmap.mmap(-1,ctypes.sizeof(NarrationShared),tagname=MAPPING_NAME)
        self.shared=NarrationShared.from_buffer(self.mapping)
        if self.shared.owner and self.shared.owner!=os.getpid():
            import psutil
            if psutil.pid_exists(self.shared.owner):
                del self.shared;self.mapping.close();raise RuntimeError('Outro Server controla as narrações')
        self.shared.version=1;self.shared.owner=os.getpid();self.shared.phase=0
        self.shared.ack=self.shared.command;self.shared.status=0;self.shared.error=0
        self.current='Tiago Leifert';self.pending=None;self.deadline=0;self.next_inject=0;self.pid=0;self.game_pid=0;self.error=''
        self._inject_results=queue.Queue();self._injecting=False
        self._profiles_cache=None;self._profiles_until=0
        self._diagnostics=None
        self._auto_context=None;self._seen_context=None;self._context_since=0;self._manual_context=None;self._previous_auto=None

    def profiles(self):
        if self._profiles_cache is not None and time.monotonic()<self._profiles_until:
            return self._profiles_cache
        result=[]
        for folder in profile_directories(self.root):
            try:
                meta=json.loads((folder/'profile.json').read_text(encoding='utf8'))
                metadata=folder/'narrator.txt'
                if metadata.exists():
                    values=dict(line.split('=',1) for line in metadata.read_text(encoding='utf-8-sig').splitlines() if '=' in line)
                    meta['name']=values.get('Narrador',meta['name']).strip() or meta['name']
                    meta['commentator']=values.get('Comentarista',meta.get('commentator','')).strip()
                package=(folder/meta.get('package','profile.npack')).resolve()
                if package.parent!=folder.resolve() or not package.is_file():continue
                portrait=(folder/meta.get('portrait','portrait.png')).resolve()
                result.append(dict(name=meta['name'],commentator=meta.get('commentator',''),path=package,mapped=meta.get('mapped',0),competitions=meta.get('competitions',[]),portrait=str(portrait) if portrait.parent==folder.resolve() and portrait.is_file() else ''))
            except (OSError,ValueError,KeyError):continue
        self._profiles_until=time.monotonic()+2
        self._profiles_cache=sorted(result,key=lambda r:({'Tiago Leifert':0,'Vilani':1,'Luiz Roberto':2}.get(r['name'],3),r['name']))
        return self._profiles_cache

    def tick(self,prematch=False):
        self.shared.heartbeat=ctypes.windll.kernel32.GetTickCount()&0xffffffff
        self.shared.phase=1 if prematch else 2
        pid=self.app._resolve_fifa_pid() if self.app.memory.is_open() else 0
        if pid!=self.game_pid:
            self.game_pid=pid;self.pid=0;self.next_inject=0
            self.current='Tiago Leifert';self.pending=None;self.error=''
            self.shared.ack=self.shared.command;self.shared.status=0;self.shared.error=0
            self.shared.ready=0
            self._restoring_default=True
        game_ready=bool(getattr(self.app,'lastpagename','ready'))
        while True:
            try:completed_pid,success,detail=self._inject_results.get_nowait()
            except queue.Empty:break
            self._injecting=False
            if completed_pid==self.game_pid:
                if success:self.pid=completed_pid
                elif detail:self.app.log('Narration DLL unavailable: '+detail)
        if pid and game_ready and pid!=self.pid and not self._injecting and time.monotonic()>=self.next_inject:
            resources=Path(getattr(self.app,'resource_dir',self.app.base_dir))
            dll=resources/'bin/fifa16_narration.dll'
            helper=resources/'bin/cgfs16_inject.exe'
            self._injecting=True
            self.next_inject=time.monotonic()+5
            def connect(target_pid=pid):
                success=False;detail=''
                try:
                    if narration_dll_loaded(target_pid):success=True
                    elif dll.exists() and helper.exists():
                        run=subprocess.run([str(helper),str(target_pid),str(dll)],capture_output=True,timeout=8,creationflags=0x08000000)
                        success=run.returncode==0
                        detail=run.stderr.decode(errors='replace')
                except (OSError,subprocess.TimeoutExpired) as exc:detail=str(exc)
                finally:self._inject_results.put((target_pid,success,detail))
            threading.Thread(target=connect,name='narration-connect',daemon=True).start()
        if self.pending is not None and self.shared.ack==self.shared.command:
            if self.shared.status==2:
                self.current=self.pending;self.error=''
                self.default_narrator=self.current
                if hasattr(self,'preferences_path'):
                    try:save_preferences(self.preferences_path,self.current)
                    except OSError as exc:self.app.log('Could not save narrator preference: '+str(exc))
                callback=getattr(self.app,'show_narration_applied',None)
                if callable(callback):callback(self.current)
            else:
                self.error=f'Perfil não aplicado (erro {self.shared.error}).'
                callback=getattr(self.app,'show_narration_loading',None)
                if callable(callback):callback(self.pending,0,self.error)
            self.pending=None
        elif self.pending is not None and time.monotonic()>self.deadline:
            self.error='A DLL ainda não confirmou a aplicação. Aguarde.'
            # Keep request pending: a late ack must not be misreported or replaced.
        diagnostics=(self.shared.ready,self.shared.status,self.shared.error,self.shared.replaced)
        previous=self._diagnostics
        if previous is None or diagnostics[:3]!=previous[:3] or (diagnostics[3]>0 and (previous[3]==0 or diagnostics[3]-previous[3]>=10)):
            self.app.log(f'Narration: ready={diagnostics[0]} status={diagnostics[1]} error={diagnostics[2]} reads={self.shared.reads} replaced={diagnostics[3]}')
            self._diagnostics=diagnostics
        self._auto_select(prematch)

    def _context(self):
        return (self.game_pid,getattr(self.app,'_kickoff_generation',0),getattr(self.app,'HID',''),getattr(self.app,'AID',''),getattr(self.app,'TOURNAME',''),getattr(self.app,'TOURROUNDID',''))

    def _auto_select(self,prematch):
        if not prematch or not self.shared.ready or self.pending is not None:return
        context=self._context()
        if not context[2] or not context[3]:return
        if context!=getattr(self,'_seen_context',None):self._seen_context=context;self._context_since=time.monotonic();return
        if time.monotonic()-getattr(self,'_context_since',0)<.8:return
        if context in (getattr(self,'_auto_context',None),getattr(self,'_manual_context',None)):return
        profiles=self.profiles();chosen=None
        default=getattr(self,'default_narrator',self.current)
        allowed=[p for p in profiles if str(context[4]) in [str(k) for k in p.get('competitions',[])]]
        if getattr(self,'_restoring_default',False):chosen=next((p for p in profiles if p['name']==default and (not allowed or p in allowed)),None)
        if chosen is None:chosen=choose_profile(profiles,context[4],getattr(self,'_previous_auto',None))
        if chosen is None:chosen=next((p for p in profiles if p['name']==default),None)
        if chosen is None:return
        try:
            self.apply(chosen['name'],automatic=True);self._auto_context=context
            self._restoring_default=False
            if chosen.get('competitions'):self._previous_auto=chosen['name']
        except (RuntimeError,ValueError) as exc:self.app.log('Automatic narration unavailable: '+str(exc))

    def apply(self,name,automatic=False):
        if self.pending is not None:raise RuntimeError('Aguarde a aplicação em andamento')
        if self.shared.phase!=1:raise RuntimeError('A troca está disponível somente antes da partida')
        if not self.shared.ready:raise RuntimeError('A DLL de narração ainda não está conectada')
        item=next((p for p in self.profiles() if p['name']==name),None)
        if item is None:raise RuntimeError('Pacote de narração não encontrado')
        path=str(item['path'])
        if len(path)>=1024:raise ValueError('Caminho de narração muito longo')
        self.shared.package=path;self.shared.status=0;self.shared.error=0
        self.pending=name;self.error='';self.deadline=time.monotonic()+30
        if not automatic:self._manual_context=self._context()
        callback=getattr(self.app,'show_narration_loading',None)
        if callable(callback):callback(name,5,'Carregando os áudios completos…')
        self.shared.command=(self.shared.command+1)&0xffffffff

    def close(self):
        self.shared.owner=0
        del self.shared;self.mapping.close()

def narration_runtime(app):
    runtime=getattr(app,'_narration_runtime',None)
    if runtime is None:
        runtime=NarrationRuntime(app);app._narration_runtime=runtime
    return runtime
