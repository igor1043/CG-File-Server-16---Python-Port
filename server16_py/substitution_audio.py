"""Club-specific substitution tracks mixed over FIFA's original audio."""
from pathlib import Path
from dataclasses import dataclass
import configparser,ctypes,hashlib,json,math,threading,time,os,tempfile
from .substitution_events import MatchReader,SubstitutionTracker
from .match_state import outside_match_page,pause_page


@dataclass(frozen=True)
class Settings:
    enabled:bool=True
    volume:float=.20
    max_seconds:int=120
    poll_ms:int=100


def read_settings(path):
    parser=configparser.ConfigParser(interpolation=None)
    parser.read(path,encoding='utf-8-sig')
    if not parser.has_section('substitution_audio'):return Settings()
    s=parser['substitution_audio'];volume=s.getfloat('volume',.20)
    if not math.isfinite(volume) or not 0<=volume<=1:raise ValueError('volume deve estar entre 0 e 1')
    return Settings(s.getboolean('enabled',True),volume,max(1,min(600,s.getint('max_seconds',120))),max(50,min(1000,s.getint('poll_ms',100))))


def save_settings(path,*,volume=None,enabled=None):
    """Persist the audio controls, preserving other options and sections."""
    path=Path(path)
    current=read_settings(path)  # Never overwrite malformed user settings.
    if volume is not None and (isinstance(volume,bool) or not isinstance(volume,(int,float)) or not math.isfinite(volume) or not 0<=volume<=1):raise ValueError('Volume deve estar entre 0 e 100%.')
    if enabled is not None and not isinstance(enabled,bool):raise ValueError('Estado de ativação inválido.')
    parser=configparser.ConfigParser(interpolation=None);parser.read(path,encoding='utf-8-sig')
    if not parser.has_section('substitution_audio'):parser.add_section('substitution_audio')
    section=parser['substitution_audio']
    section['volume']=format(current.volume if volume is None else volume,'.4f')
    section['enabled']='true' if (current.enabled if enabled is None else enabled) else 'false'
    path.parent.mkdir(parents=True,exist_ok=True);temporary=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,prefix=path.name+'.',suffix='.tmp',delete=False) as out:
            temporary=Path(out.name);parser.write(out);out.flush();os.fsync(out.fileno())
        os.replace(temporary,path)
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)
    return read_settings(path)


class AudioSession:
    def __init__(self,game,player_factory,log=lambda *a,**k:None):
        self.game=Path(game);self.player_factory=player_factory;self.log=log;self.settings=Settings();self.tracker=SubstitutionTracker();self.player=None;self.club=0;self.started=0;self.paused=False;self.pause_at=0;self.last_valid=None;self.identity=None;self.signal=None;self.playback_volume=None
    def stop(self,reason):
        if self.player:
            for action in (self.player.stop,self.player.close):
                try:action()
                except Exception:pass
            self.log('stopped',reason=reason,club=self.club)
        self.player=None;self.club=0;self.paused=False
    def reset(self,reason):self.stop(reason);self.tracker.reset();self.identity=None;self.last_valid=None;self.signal=None
    def observe(self,snapshot,now):
        if not self.settings.enabled:self.reset('disabled');return
        if snapshot is None:
            if self.last_valid is not None and now-self.last_valid>=1:self.reset('match_unavailable')
            return
        self.last_valid=now
        if outside_match_page(snapshot.page):self.reset('left_match');return
        # Phase 0 is also used by the native substitution sequence. Keep the
        # committed roster through temporary scene phases and explicit menus.
        if self.identity!=snapshot.identity:
            self.reset('new_match');self.identity=snapshot.identity;self.last_valid=now
            self.log('match_bound',clubs=snapshot.clubs,players=len(snapshot.players),clock=snapshot.clock)
        signal=(snapshot.phase,snapshot.replay,snapshot.page,snapshot.presentation,self.tracker.active_rosters(snapshot))
        if signal!=self.signal:
            self.signal=signal
            self.log('signal',phase=snapshot.phase,replay=snapshot.replay,page=snapshot.page,presentation=snapshot.presentation,paused=snapshot.paused,active=signal[-1],clock=snapshot.clock)
        paused=snapshot.paused
        if self.player:
            try:
                if self.playback_volume!=self.settings.volume:
                    self.player.set_volume(self.settings.volume);self.playback_volume=self.settings.volume
                    self.log('volume_changed',club=self.club,volume=self.settings.volume)
                if paused and not self.paused:self.player.pause();self.paused=True;self.pause_at=now
                elif not paused and self.paused:self.player.resume();self.started+=now-self.pause_at;self.paused=False
                if not self.paused and (self.player.mode() in ('stopped','closed') or now-self.started>=self.settings.max_seconds):self.stop('track_finished')
            except Exception as exc:self.log('playback_error',error=str(exc));self.stop('decoder_error')
        events=self.tracker.observe(snapshot)
        for event in events:
            self.log('substitution',club=event.club,side=event.side,incoming=event.incoming,outgoing=event.outgoing,clock=event.clock)
            if event.side!=0:
                self.log('away_substitution_ignored',club=event.club)
                continue
            track=self.game/'FSW/Substitutions'/(str(event.club)+'.mp3')
            if not track.is_file():self.log('track_missing',club=event.club);continue
            if self.player and self.club==event.club:self.log('coalesced',club=event.club);continue
            # Simultaneous substitutions on both sides must not stack players.
            if self.player:self.log('audio_busy',club=event.club);continue
            player=None
            try:
                player=self.player_factory();player.open(track);player.set_volume(self.settings.volume);player.play()
                self.player=player;self.club=event.club;self.started=now;self.paused=False;self.playback_volume=self.settings.volume
                self.log('playing',club=event.club,track=str(track.relative_to(self.game)),volume=self.settings.volume)
            except Exception as exc:
                if player:
                    try:player.close()
                    except Exception:pass
                self.log('track_error',club=event.club,error=str(exc))
    def close(self):self.reset('shutdown')


class SubstitutionAudioRuntime:
    """One owned worker/READ handle, independent from the crowd chant loop."""
    def __init__(self,app):
        self.app=app;self.game=Path(app.exedir);self.stop_event=threading.Event();self.thread=None
        self.config=self.game/'ModCarrerMode/config/substitution_audio.ini';self.log_path=self.game/'ModCarrerMode/logs/substitution_audio.log';self.config_stamp=object()
    def log(self,event,**values):
        try:
            self.log_path.parent.mkdir(parents=True,exist_ok=True)
            with self.log_path.open('a',encoding='utf8') as out:out.write(json.dumps(dict(time=time.time(),event=event,**values),ensure_ascii=False)+'\n')
        except OSError:pass
    def start(self):
        if self.thread and self.thread.is_alive():return
        self.stop_event.clear();self.thread=threading.Thread(target=self.run,name='substitution-audio',daemon=True);self.thread.start()
    def close(self):
        self.stop_event.set()
        if self.thread and self.thread is not threading.current_thread():self.thread.join(timeout=2)
    def run(self):
        import psutil
        from .memory_access import Memory
        from .chants_runtime import MciAudioPlayer
        from ctypes import wintypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.CreateMutexW.argtypes=[ctypes.c_void_p,wintypes.BOOL,wintypes.LPCWSTR];kernel.CreateMutexW.restype=wintypes.HANDLE
        kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        key=hashlib.sha256(str(self.game.resolve()).casefold().encode()).hexdigest()[:20]
        lock=None;waiting=False
        while not self.stop_event.is_set():
            lock=kernel.CreateMutexW(None,False,'Local\\Server16SubstitutionAudio_v2_'+key)
            if not lock:return
            if ctypes.get_last_error()!=183:break
            kernel.CloseHandle(lock);lock=None
            if not waiting:self.log('already_running',revision=2);waiting=True
            self.stop_event.wait(1)
        if not lock:return
        session=AudioSession(self.game,MciAudioPlayer,self.log);memory=None;process=None;reader=None;next_config=0;next_connect=0;last_error=None
        self.log('started',revision=2,mode='read_only_roster_and_native_presentation',folder='FSW/Substitutions')
        try:
            while not self.stop_event.is_set():
                now=time.monotonic()
                if now>=next_config:
                    next_config=now+1
                    try:
                        stamp=(self.config.stat().st_mtime_ns,self.config.stat().st_size) if self.config.exists() else None
                        if stamp!=self.config_stamp:
                            session.settings=read_settings(self.config);self.config_stamp=stamp;self.log('settings',**vars(session.settings))
                    except (OSError,ValueError,configparser.Error) as exc:
                        session.settings=Settings(enabled=False)
                        if str(exc)!=last_error:self.log('settings_error',error=str(exc));last_error=str(exc)
                if memory is not None:
                    try:alive=process.is_running()
                    except psutil.Error:alive=False
                    if not alive:session.reset('game_closed');memory.close();memory=reader=process=None
                if memory is None and now>=next_connect:
                    next_connect=now+1
                    for candidate in psutil.process_iter(['name','exe']):
                        try:
                            if (candidate.info['name'] or '').casefold()!='fifa16.exe' or not candidate.info['exe'] or Path(candidate.info['exe']).resolve().parent!=self.game.resolve():continue
                            probe=Memory();probe.process_id=candidate.pid;probe.process_handle=probe.kernel32.OpenProcess(0x410,False,candidate.pid)
                            probe.base_module=probe._get_base_address(candidate.info['exe'])
                            if not probe.process_handle or not probe.base_module:probe.close();continue
                            memory=probe;process=candidate;reader=MatchReader(memory);self.log('attached',pid=candidate.pid);break
                        except (psutil.Error,OSError):continue
                try:session.observe(reader.read() if reader and session.settings.enabled else None,now)
                except Exception as exc:
                    if str(exc)!=last_error:self.log('observation_error',error=str(exc));last_error=str(exc)
                    session.observe(None,now)
                self.stop_event.wait(session.settings.poll_ms/1000)
        finally:
            session.close()
            if memory:memory.close()
            kernel.CloseHandle(lock)
            self.log('closed')
