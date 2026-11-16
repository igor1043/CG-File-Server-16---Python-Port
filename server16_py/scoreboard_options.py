"""Native match options for video, attendance and stadium; scoreboard is INI-only.

The historical class/module name is retained for existing stadium integrations.
Old scoreboard.ini preferences and native scoreboard request files are ignored.
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib,json,struct,threading
from .file_tools import replace_asset_file

PAGE='game/screens/settings/GameSettings'
UI_PATH='data/ui/game/screens/settings/gamesettings.big'
CATALOG='ModCarrerMode/data/match_options/catalog.json'

def verified_ui(game,record):
    """Refuse to overwrite UI bytes owned by a concurrent integration."""
    game=Path(game)
    if record.get('schema')!=1 or record.get('native_options_revision')!=4 or record.get('scoreboard_selectable') is not False:raise ValueError('Catálogo do seletor inválido')
    data=bytearray((game/UI_PATH).read_bytes());offset=record['movie_initial_offset']
    if not isinstance(offset,int) or not 1<=offset<=len(data)-4 or data[offset-1]!=183:raise ValueError('Posição do seletor inválida')
    stable=bytearray(data)
    for mutable in record.get('mutable_value_offsets',[offset]):
        if not isinstance(mutable,int) or not 1<=mutable<=len(data)-4 or data[mutable-1]!=183:raise ValueError('Posição do seletor inválida')
        stable[mutable:mutable+4]=bytes(4)
    if hashlib.sha256(stable).hexdigest()!=record['ui_stable_sha256']:raise ValueError('A tela foi alterada por outra revisão; atualização interrompida')
    return data,offset


def update_movie_initial(game,catalog):
    from .movie_options import selected_index as movie_index
    game=Path(game);record=json.loads((game/CATALOG).read_bytes())
    if record.get('movie_signature')!=catalog.signature:raise ValueError('Lista de vídeos desatualizada')
    data,_=verified_ui(game,record);offset=record['movie_initial_offset'];value=movie_index(game,catalog)
    if struct.unpack_from('<i',data,offset)[0]==value:return
    struct.pack_into('<i',data,offset,value);path=game/UI_PATH;temp=path.with_suffix('.big.movie-new');temp.write_bytes(data);replace_asset_file(temp,path)


class ScoreboardOptions:
    """One serialized background worker; copies never run in the UI poll."""
    def __init__(self,app):
        self.app=app;self.executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='Server16Scoreboard')
        self.root=None;self.stamp=None;self.bound=False;self.closed=False;self.owner_pid=0
        self._pending=0;self._lock=threading.Lock()
        self.enter_stamp=None;self.open_stamp=None;self.last_page=None;self.movie_stamp=None
        self.stadium=None;self.stadium_context=None

    @property
    def busy(self):
        with self._lock:return self._pending>0

    def _submit(self,function,*args):
        if self.closed:return
        with self._lock:self._pending+=1
        def complete(unused):
            with self._lock:self._pending-=1
        try:self.executor.submit(function,*args).add_done_callback(complete)
        except RuntimeError:
            complete(None)
            if not self.closed:raise

    def bind(self,game):
        game=Path(game)
        if self.root==game:return
        self.root=game;self.stamp=None;self.bound=False
        self._submit(self._prepare,game)

    def _prepare(self,game,refresh=None):
        try:
            from . import movie_options
            movies=movie_options.discover(game)
            manifest=game/CATALOG;rebuild=True
            if manifest.is_file():
                record=json.loads(manifest.read_bytes())
                if (game/UI_PATH).is_file():verified_ui(game,record)
                rebuild=(record.get('movie_signature')!=movies.signature
                    or record.get('native_options_revision')!=4 or record.get('scoreboard_selectable') is not False
                    or record.get('stadium_revision')!=self.stadium or not (game/UI_PATH).is_file())
            if rebuild:
                from .scoreboard_options_ui import build
                template=game/'ModCarrerMode/source/native_mods/scoreboard_settings/gamesettings.original.big'
                if not template.is_file():raise FileNotFoundError('Modelo da tela de opções não instalado')
                build(game,template,game/UI_PATH,manifest,stadium=self.stadium)
            update_movie_initial(game,movies)
            if self.root==game:self.bound=True
            if rebuild and refresh:
                from .stadium_options import publish_refresh
                publish_refresh(self.app,refresh)
        except Exception as error:self.app.log('Native match options initialization failed',error)

    def poll(self,page):
        if self.closed or not self.bound:return
        pid=getattr(self.app.memory,'process_id',0)
        if not pid:return
        if pid!=self.owner_pid:
            self.owner_pid=pid;self._submit(self._prepare,self.root)
        from .stadium_options import poll_native_options
        poll_native_options(self,page,pid)
        from . import movie_options
        movie_path=self.root/movie_options.REQUEST
        try:
            info=movie_path.stat();stamp=(pid,info.st_mtime_ns,info.st_size)
            if stamp!=self.movie_stamp:
                self.movie_stamp=stamp;self._submit(self._apply_movie,self.root,pid)
        except FileNotFoundError:pass
    def _apply_movie(self,game,pid):
        if self.closed or self.root!=game or self.app.memory.process_id!=pid:return
        try:
            from . import movie_options
            if not self.app.module_enabled('Movies'):raise RuntimeError('Ative o módulo Movies no Server16')
            if movie_options.adopt_pending(self.app):
                update_movie_initial(game,movie_options.discover(game));self.app.apply_movie_runtime()
                self.app.log('Pre-match movie chosen in native game options')
        except Exception as error:self.app.log('Failed to apply native movie choice',error)

    def stadium_applied(self,name,slot):
        from .stadium_options import applied_stadium
        applied_stadium(self,name,slot)

    def close(self):
        self.closed=True;self.executor.shutdown(wait=False,cancel_futures=True)
