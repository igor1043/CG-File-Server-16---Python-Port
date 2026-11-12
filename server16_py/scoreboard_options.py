"""Manual pre-match scoreboard choice, independent of competition assignments."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import configparser
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import threading

PAGE='game/screens/settings/GameSettings'
UI_PATH='data/ui/game/screens/settings/gamesettings.big'
CATALOG='ModCarrerMode/data/scoreboard_selector/catalog.json'
PREFERENCE='ModCarrerMode/config/scoreboard.ini'
REQUEST='ModCarrerMode/runtime/scoreboard_selector/request.tsv'
ACK='ModCarrerMode/runtime/scoreboard_selector/ack.json'
MAX_OPTIONS=1024


def valid_name(name):
    return isinstance(name,str) and bool(name) and name not in ('.','..') and not any(c in name for c in '/\\:\r\n\0')


@dataclass(frozen=True)
class Catalog:
    packages:tuple[str,...]

    @property
    def signature(self):return hashlib.sha256(json.dumps(self.packages,ensure_ascii=True).encode()).hexdigest()
    @property
    def labels(self):return ('Automático · Server16','Padrão do FIFA',*self.packages)
    @property
    def values(self):return (None,'',*self.packages)


def discover(game):
    base=Path(game)/'ScoreBoardGBD'
    packages=tuple(sorted((p.name for p in base.iterdir() if p.is_dir() and valid_name(p.name)),key=str.casefold)) if base.is_dir() else ()
    if len(packages)>MAX_OPTIONS-2:raise ValueError('Há mais placares que o seletor suporta')
    return Catalog(packages)


def load_choice(game):
    path=Path(game)/PREFERENCE
    if not path.is_file():return None
    if path.stat().st_size>4096:raise ValueError('Arquivo de escolha de placar inválido')
    ini=configparser.ConfigParser(interpolation=None);ini.read(path,encoding='utf-8-sig')
    mode=ini.get('Scoreboard','Mode',fallback='automatic')
    if mode=='automatic':return None
    if mode=='native':return ''
    name=ini.get('Scoreboard','Package',fallback='')
    if mode!='manual' or not valid_name(name):raise ValueError('Placar manual inválido')
    # A removed package cannot block future matches or name another path.
    return name if (Path(game)/'ScoreBoardGBD'/name).is_dir() else None


def save_choice(game,choice):
    if choice is not None and choice!='' and (not valid_name(choice) or not (Path(game)/'ScoreBoardGBD'/choice).is_dir()):raise ValueError('Placar não instalado')
    mode='automatic' if choice is None else 'native' if choice=='' else 'manual'
    text='[Scoreboard]\nMode='+mode+'\n'
    if mode=='manual':text+='Package='+choice+'\n'
    path=Path(game)/PREFERENCE;path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.ini.new');temp.write_text(text,encoding='utf8');os.replace(temp,path)


def selected_index(game,catalog):
    choice=load_choice(game)
    try:return catalog.values.index(choice)
    except ValueError:return 0


def resolve(game,assigned):
    choice=load_choice(game)
    return assigned if choice is None else choice


def verified_ui(game,record):
    """Refuse to overwrite UI bytes owned by a concurrent integration."""
    game=Path(game)
    if record.get('schema')!=1:raise ValueError('Catálogo do seletor inválido')
    data=bytearray((game/UI_PATH).read_bytes());offset=record['initial_value_offset']
    if not isinstance(offset,int) or not 1<=offset<=len(data)-4 or data[offset-1]!=183:raise ValueError('Posição do seletor inválida')
    stable=bytes(data[:offset])+bytes(4)+bytes(data[offset+4:])
    if hashlib.sha256(stable).hexdigest()!=record['ui_stable_sha256']:raise ValueError('A tela foi alterada por outra revisão; atualização interrompida')
    return data,offset


def update_initial_choice(game,catalog):
    """Change only our verified AVM integer; preserve every other UI byte."""
    game=Path(game);record=json.loads((game/CATALOG).read_bytes())
    if record.get('signature')!=catalog.signature:raise ValueError('Lista do seletor desatualizada')
    data,offset=verified_ui(game,record)
    value=selected_index(game,catalog)
    if struct.unpack_from('<i',data,offset)[0]==value:return
    struct.pack_into('<i',data,offset,value)
    path=game/UI_PATH;temp=path.with_suffix('.big.scoreboard-new');temp.write_bytes(data);os.replace(temp,path)


def _request(game,pid,created):
    path=Path(game)/REQUEST
    if path.stat().st_size>512:raise ValueError('Solicitação de placar excedeu o limite')
    with path.open('rb') as stream:raw=stream.read(513)
    if len(raw)>512:raise ValueError('Solicitação de placar excedeu o limite')
    fields=dict(line.split('=',1) for line in raw.decode('ascii').splitlines() if '=' in line)
    if fields.get('schema')!='1' or int(fields.get('pid','0'))!=pid or abs(int(fields.get('created','0'))-created)>10000:raise ValueError('Solicitação pertence a outra sessão')
    match=re.fullmatch(r'S16SCORE1\|([0-9a-f]{64})\|(0|[1-9]\d{0,3})\|END',fields.get('wire',''))
    if not match:raise ValueError('Solicitação de placar inválida')
    catalog=discover(game);index=int(match[2])
    if match[1]!=catalog.signature or not 0<=index<len(catalog.values):raise ValueError('Catálogo de placares mudou; abra novamente as opções')
    return catalog,index,hashlib.sha256(raw).hexdigest()


def read_request(game,pid,created):return _request(game,pid,created)[:2]


def adopt_pending(app):
    """Also run at presentation preparation, so a fast Start cannot beat polling."""
    game=Path(app.exedir);pid=getattr(getattr(app,'memory',None),'process_id',0)
    if not pid or not (game/REQUEST).is_file():return False
    try:
        import psutil
        created=round((psutil.Process(pid).create_time()+11644473600)*10_000_000)
        catalog,index,identity=_request(game,pid,created)
    except (OSError,ValueError,psutil.Error):return False
    ack=game/ACK
    try:
        if ack.stat().st_size<=512 and json.loads(ack.read_bytes()).get('request')==identity:return False
    except (OSError,ValueError,AttributeError):pass
    save_choice(game,catalog.values[index])
    if (game/CATALOG).is_file():
        try:update_initial_choice(game,catalog)
        except (OSError,ValueError,KeyError) as error:app.log('Scoreboard selected; UI initial value requires rebuilding',error)
    ack.parent.mkdir(parents=True,exist_ok=True);temp=ack.with_suffix('.json.new')
    temp.write_text(json.dumps(dict(schema=1,pid=pid,request=identity)),encoding='ascii');os.replace(temp,ack)
    return True


class ScoreboardOptions:
    """One serialized background worker; copies never run in the UI poll."""
    def __init__(self,app):
        self.app=app;self.executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='Server16Scoreboard')
        self.root=None;self.stamp=None;self.bound=False;self.closed=False;self.owner_pid=0
        self._pending=0;self._lock=threading.Lock()

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

    def _prepare(self,game):
        try:
            catalog=discover(game);manifest=game/CATALOG;rebuild=True
            if manifest.is_file():
                record=json.loads(manifest.read_bytes())
                if (game/UI_PATH).is_file():verified_ui(game,record)
                rebuild=record.get('signature')!=catalog.signature or record.get('crowd_row')!=65001 or not (game/UI_PATH).is_file()
            if rebuild:
                from .scoreboard_options_ui import build
                template=game/'ModCarrerMode/source/native_mods/scoreboard_settings/gamesettings.original.big'
                if not template.is_file():raise FileNotFoundError('Modelo da tela de placares não instalado')
                build(game,template,game/UI_PATH,manifest)
            update_initial_choice(game,catalog)
            if self.root==game:self.bound=True
        except Exception as error:self.app.log('Scoreboard selector initialization failed',error)

    def poll(self,page):
        if self.closed or not self.bound:return
        pid=getattr(self.app.memory,'process_id',0)
        if not pid:return
        if pid!=self.owner_pid:
            self.owner_pid=pid;self._submit(self._prepare,self.root)
        path=self.root/REQUEST
        try:
            info=path.stat();stamp=(pid,info.st_mtime_ns,info.st_size)
            if stamp==self.stamp:return
            self.stamp=stamp
            import psutil
            created=round((psutil.Process(pid).create_time()+11644473600)*10_000_000)
            catalog,index=read_request(self.root,pid,created)
            self._submit(self._apply,self.root,pid,catalog,index)
        except FileNotFoundError:pass
        except Exception as error:self.app.log('Scoreboard selector request rejected',error)

    def _apply(self,game,pid,catalog,index):
        if self.closed or self.root!=game or self.app.memory.process_id!=pid:return
        try:
            if not self.app.module_enabled('ScoreBoard'):raise RuntimeError('Ative o módulo ScoreBoard no Server16 para aplicar o placar')
            save_choice(game,catalog.values[index])
            try:update_initial_choice(game,catalog)
            except (OSError,ValueError,KeyError) as error:self.app.log('Scoreboard selected; UI value will be refreshed on next launch',error)
            # Existing Server16 baseline/TV-logo variants/progress notifications.
            self.app.apply_scoreboard_runtime()
            self.app.log('Scoreboard chosen in native game options: '+catalog.labels[index])
        except Exception as error:self.app.log('Failed to apply native scoreboard choice',error)

    def close(self):
        self.closed=True;self.executor.shutdown(wait=False,cancel_futures=True)
