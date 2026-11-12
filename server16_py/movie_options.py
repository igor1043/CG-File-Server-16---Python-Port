"""Manual pre-match video selection; retain automatic competition assignments."""
from pathlib import Path
from dataclasses import dataclass
import configparser,hashlib,json,os,re
from .presentation_options_catalog import packages,available

REQUEST='ModCarrerMode/runtime/movie_selector/request.tsv'
ACK='ModCarrerMode/runtime/movie_selector/ack.json'
PREFERENCE='ModCarrerMode/config/movie.ini'

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
    names=packages(game,'MoviesGBD','movies',{'movies','teammovies','derbymatch','moviecatalog'})
    if len(names)>1022:raise ValueError('Catálogo de vídeos excedeu o limite')
    return Catalog(names)

def load_choice(game):
    p=Path(game)/PREFERENCE
    if not p.is_file():return None
    if p.stat().st_size>4096:raise ValueError('Configuração de vídeo inválida')
    ini=configparser.ConfigParser(interpolation=None);ini.read(p,encoding='utf-8-sig')
    mode=ini.get('Movie','Mode',fallback='automatic')
    if mode=='automatic':return None
    if mode=='native':return ''
    name=ini.get('Movie','Package',fallback='')
    if mode!='manual':raise ValueError('Configuração de vídeo inválida')
    return name if available(game,'MoviesGBD','movies',name) else None

def save_choice(game,choice):
    if choice not in (None,'') and not available(game,'MoviesGBD','movies',choice):raise ValueError('Vídeo não instalado')
    ini=configparser.ConfigParser(interpolation=None);ini['Movie']={'Mode':'automatic' if choice is None else 'native' if choice=='' else 'manual'}
    if choice:ini['Movie']['Package']=choice
    p=Path(game)/PREFERENCE;p.parent.mkdir(parents=True,exist_ok=True);temp=p.with_suffix('.ini.new')
    with temp.open('w',encoding='utf8') as f:ini.write(f)
    os.replace(temp,p)

def selected_index(game,catalog):
    try:return catalog.values.index(load_choice(game))
    except ValueError:return 0

def read_request(game,pid,created):
    p=Path(game)/REQUEST
    if p.stat().st_size>512:raise ValueError('Solicitação de vídeo inválida')
    raw=p.read_bytes();fields=dict(s.split('=',1) for s in raw.decode('ascii').splitlines() if '=' in s)
    if fields.get('schema')!='1' or int(fields.get('pid','0'))!=pid or abs(int(fields.get('created','0'))-created)>10000:raise ValueError('Solicitação de outra sessão')
    match=re.fullmatch(r'S16MOVIE1\|([0-9a-f]{64})\|(0|[1-9]\d{0,3})\|END',fields.get('wire',''))
    cat=discover(game)
    if not match or match[1]!=cat.signature or not 0<=int(match[2])<len(cat.values):raise ValueError('Catálogo de vídeos mudou; reabra as opções')
    return cat,int(match[2]),hashlib.sha256(raw).hexdigest()

def adopt_pending(app):
    pid=getattr(getattr(app,'memory',None),'process_id',0);root=Path(app.exedir)
    if not pid or not (root/REQUEST).is_file():return False
    import psutil
    try:
        created=round((psutil.Process(pid).create_time()+11644473600)*10_000_000)
        cat,index,identity=read_request(root,pid,created)
        try:
            if json.loads((root/ACK).read_bytes()).get('request')==identity:return False
        except (OSError,ValueError,AttributeError):pass
        save_choice(root,cat.values[index]);p=root/ACK;p.parent.mkdir(parents=True,exist_ok=True)
        temp=p.with_suffix('.new');temp.write_text(json.dumps({'request':identity}));os.replace(temp,p);return True
    except (OSError,ValueError,psutil.Error):return False
