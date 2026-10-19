"""One competition-ID artwork library for calendar and career cards."""
from __future__ import annotations
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import struct
import tempfile
import threading
import time
import unicodedata
from PIL import Image, ImageOps
from .competition_catalog import COMP_OBJ, ICON_MAP, icon_mapping, settings_text, nodes, visual

ICONS=Path('data/ui/imgAssets/careerCompetitionIcons')
EXTENSIONS={'.png','.jpg','.jpeg','.webp','.bmp','.dds'}

def digest(data):return hashlib.sha256(data).hexdigest()
def normalized(name):
    text=unicodedata.normalize('NFKD',name.casefold())
    return re.sub(r'[^a-z0-9]+',' ',''.join(c for c in text if not unicodedata.combining(c))).strip()
def identities(game):
    mapping={ident:ident for ident,row in nodes(game).items() if row[0]==3}
    labels,aliases={},{}
    path=Path(game)/'FSW/settings.ini'
    if path.is_file():
        text=settings_text(path)
        for section in ('Scoreboard','movies'):
            block=re.search(r'^\['+section+r'\][ \t]*\r?\n(.*?)(?=^\[|\Z)',text,re.M|re.S|re.I)
            if not block:continue
            for line in block[1].splitlines():
                match=re.match(r'^\s*(\d+)\s*=(.*)',line)
                if not match or int(match[1]) not in mapping:continue
                key,label=int(match[1]),match[2].split(',')[0].strip()
                if label and label.casefold() not in ('none','default'):
                    labels[key]=label;aliases.setdefault(normalized(label),set()).add(key)
    return mapping,labels,aliases

def resolve(stem,mapping,aliases):
    match=re.fullmatch(r'(?:c)?(\d+)(?:\s*[-_]\s*.+)?',stem,re.I)
    if match and int(match[1]) in mapping:return int(match[1])
    candidates=aliases.get(normalized(stem),set())
    if len(candidates)==1:return next(iter(candidates))
    raise ValueError('competição não identificada; use o ID ou um nome de COMPETICOES.txt')

def convert(raw,kind='calendar'):
    with Image.open(io.BytesIO(raw)) as original:
        original.load();image=ImageOps.exif_transpose(original).convert('RGBA')
    bounds=image.getchannel('A').getbbox()
    if not bounds:raise ValueError('imagem totalmente transparente')
    image=image.crop(bounds)
    canvas=Image.new('RGBA',(128,128) if kind=='calendar' else (256,256))
    box=48 if kind=='calendar' else 256
    image.thumbnail((box-2,box-2),Image.Resampling.LANCZOS)
    canvas.paste(image,((box-image.width)//2,(box-image.height)//2))
    data=encode_native_dds(canvas)
    expected=16512 if kind=='calendar' else 65664
    if len(data)!=expected or data[:4]!=b'DDS ' or data[84:88]!=b'DXT5':raise ValueError('DDS DXT5 inválido')
    return data,','.join(map(str,canvas.getchannel('A').getbbox()))

def encode_native_dds(image):
    out=io.BytesIO();image.save(out,format='DDS',pixel_format='DXT5');data=bytearray(out.getvalue())
    # FIFA expects the BC3 top-level byte count, not Pillow's RGB row pitch.
    linear=((image.width+3)//4)*((image.height+3)//4)*16
    struct.pack_into('<I',data,20,linear)
    struct.pack_into('<I',data,88,0)
    return bytes(data)

def atomic_write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True);temporary=None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent,prefix='.'+path.name,suffix='.tmp',delete=False) as file:
            temporary=Path(file.name);file.write(data)
        os.replace(temporary,path)
    finally:
        if temporary is not None and temporary.exists():temporary.unlink()

class CompetitionIconImporter:
    def __init__(self,game,log=print):
        self.game=Path(game);self.folder=self.game/ICONS;self.log=log;self.observed={};self.reported=set()
    def _report(self,name,detail):
        key=(name,detail)
        if key not in self.reported:self.reported.add(key);self.log(f'Ícones das competições: {name}: {detail}')
    def sync(self,force=False):
        mapping,labels,aliases=identities(self.game)
        if not mapping:return 0
        self.folder.mkdir(parents=True,exist_ok=True)
        instructions=('ÍCONES DAS COMPETIÇÕES — UMA IMAGEM POR ID DO INI\n\n'
            'Use <ID>.png nesta pasta. Calendário, Central e Competições usam esta mesma imagem.\n'
            'Abra o Server16 antes do FIFA para preparar as proporções. O módulo gera o BIG do calendário ao iniciar o FIFA.\n'
            'As subpastas calendar e cards são geradas automaticamente; não as edite.\n\n')
        instructions+=''.join(f'{key} - {labels.get(key,"Competição "+str(key))}.png\n' for key in sorted(mapping))
        self._write_if_changed(self.folder/'COMPETICOES.txt',instructions.encode('utf-8-sig'))
        raw_visuals={ident:visual(row) for ident,row in nodes(self.game).items() if row[0]==3}
        for ident,art in icon_mapping(self.game).items():
            if not raw_visuals.get(ident):raw_visuals[ident]=art
        # This manifest translates legacy visual IDs at the UI boundary only.
        manifest='competition_id\tvisual_id\tlabel\n'+''.join(f'{key}\t{raw_visuals[key]}\t{labels.get(key,"")}\n' for key in sorted(mapping))
        self._write_if_changed(self.folder/'competitions.tsv',manifest.encode('utf-8'))
        pending={}
        for path in sorted(self.folder.iterdir()):
            if not path.is_file() or path.suffix.lower() not in EXTENSIONS:continue
            if path.suffix.lower()=='.dds' and re.fullmatch(r'c\d+',path.stem,re.I):continue # archived visual-ID outputs
            try:pending.setdefault(resolve(path.stem,mapping,aliases),[]).append(path)
            except ValueError as exc:self._report(path.name,str(exc))
        for kind in ('calendar','cards'):
            side=128 if kind=='calendar' else 256
            self._write_if_changed(self.folder/kind/'empty.dds',encode_native_dds(Image.new('RGBA',(side,side))))
        installed=0
        for ident,paths in pending.items():
            if len(paths)!=1:self._report(str(ident),'mais de uma imagem para o mesmo ID');continue
            path=paths[0]
            try:
                stamp=(path.stat().st_size,path.stat().st_mtime_ns);old=self.observed.get(path.name);self.observed[path.name]=stamp
                if not force and old!=stamp:continue
                raw=path.read_bytes()
                if (path.stat().st_size,path.stat().st_mtime_ns)!=stamp:continue
                updates={self.folder/kind/f'c{ident}.dds':convert(raw,kind)[0] for kind in ('calendar','cards')}
                changed={p:data for p,data in updates.items() if not p.is_file() or p.read_bytes()!=data}
                if not changed:continue
                before={p:p.read_bytes() if p.is_file() else None for p in changed}
                backup=self.game/'runtime/backups/career_competition_icons'/str(time.time_ns())
                for p,data in before.items():
                    if data is not None:atomic_write(backup/p.relative_to(self.game),data)
                try:
                    for p,data in changed.items():atomic_write(p,data)
                except Exception:
                    for p,data in before.items():
                        if data is None:p.unlink(missing_ok=True)
                        else:atomic_write(p,data)
                    raise
                installed+=1;self.log(f'Ícone {ident}: calendário e cards preparados da mesma imagem {path.name}.')
            except (OSError,ValueError,Image.DecompressionBombError) as exc:self._report(path.name,str(exc))
        return installed
    @staticmethod
    def _write_if_changed(path,data):
        if not path.is_file() or path.read_bytes()!=data:atomic_write(path,data)

class CompetitionIconService:
    """One worker, no Tk calls; writes only while FIFA is closed."""
    def __init__(self, log):
        self.log = log
        self.lock = threading.Lock()
        self.worker = None
        self.importer = None

    @property
    def busy(self):
        return self.worker is not None and self.worker.is_alive()

    def prepare(self, game, force=False):
        with self.lock:
            if self.importer is None or self.importer.game != Path(game):
                self.importer = CompetitionIconImporter(game, self.log)
            try:
                return self.importer.sync(force=force)
            except Exception as exc:
                self.importer._report('serviço', str(exc))
                return 0

    def poll(self, game, game_running):
        if game_running or self.busy:
            return
        self.worker = threading.Thread(target=self.prepare, args=(Path(game),), name='career-icon-import', daemon=True)
        self.worker.start()
