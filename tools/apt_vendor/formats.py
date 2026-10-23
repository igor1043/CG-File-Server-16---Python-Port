"""Lossless BIG edits and structural APT scene parsing for FIFA 16."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import io, math, struct, os, tempfile, hashlib, datetime, zlib
from PIL import Image

class FormatError(ValueError):
    pass

def chunk_unwrap(data):
    if data[:8]!=b'chunkzip': return data,None
    if len(data)<48: raise FormatError('chunkzip truncado.')
    version,size,block_size,count,descriptor=struct.unpack_from('>5I',data,8)
    if version!=2 or not 0<count<10000 or descriptor!=16 or not 0<block_size<=128*1024*1024 or size>128*1024*1024:
        raise FormatError('chunkzip não suportado: esta versão aceita o subtipo v2/descritor 16.')
    decoded=bytearray(); p=40
    for _ in range(count):
        if p+8>len(data): raise FormatError('Descritor chunkzip truncado.')
        length,kind=struct.unpack_from('>II',data,p); p+=8
        if kind!=1 or p+length>len(data): raise FormatError('Descritor chunkzip não suportado.')
        try: block=zlib.decompress(data[p:p+length],-15)
        except zlib.error as error: raise FormatError('Bloco DEFLATE inválido.') from error
        if len(block)>block_size: raise FormatError('Bloco chunkzip excedeu o limite.')
        decoded.extend(block); p=((p+length+8+15)//16)*16-8
    if len(decoded)!=size: raise FormatError('Tamanho chunkzip inconsistente.')
    return bytes(decoded),data[:40]

def chunk_wrap(data,header):
    block_size=struct.unpack_from('>I',header,16)[0]
    out=bytearray(header); struct.pack_into('>I',out,12,len(data)); struct.pack_into('>I',out,20,math.ceil(len(data)/block_size))
    for p in range(0,len(data),block_size):
        start=((len(out)+8+15)//16)*16-8; out.extend(b'\0'*(start-len(out)))
        compressor=zlib.compressobj(9,zlib.DEFLATED,-15)
        encoded=compressor.compress(data[p:p+block_size])+compressor.flush()
        out.extend(struct.pack('>II',len(encoded),1)); out.extend(encoded)
    return bytes(out)

def refpack(data: bytes) -> bytes:
    if len(data) < 5 or data[0] not in (0x10, 0x90) or data[1] != 0xFB:
        return data
    n = 4 if data[0] & 0x80 else 3
    size = int.from_bytes(data[2:2+n], 'big')
    if size > 128 * 1024 * 1024:
        raise FormatError('Recurso comprimido maior que 128 MB.')
    p, out = 2+n, bytearray()
    def literals(count):
        nonlocal p
        if p+count > len(data): raise FormatError('RefPack truncado.')
        out.extend(data[p:p+count]); p += count
    while p < len(data):
        c=data[p]; p+=1
        if c >= 0xFC:
            literals(c & 3); break
        if c >= 0xE0:
            literals(((c & 0x1F)+1)*4); continue
        if c >= 0xC0:
            if p+3 > len(data): raise FormatError('RefPack truncado.')
            a,b,d=data[p:p+3]; p+=3
            literal=c&3; count=((c&0x0C)<<6)+d+5
            distance=((c&0x10)<<12)+(a<<8)+b+1
        elif c >= 0x80:
            if p+2 > len(data): raise FormatError('RefPack truncado.')
            a,b=data[p:p+2]; p+=2
            literal=a>>6; count=(c&0x3F)+4; distance=((a&0x3F)<<8)+b+1
        else:
            if p >= len(data): raise FormatError('RefPack truncado.')
            a=data[p]; p+=1
            literal=c&3; count=((c&0x1C)>>2)+3; distance=((c&0x60)<<3)+a+1
        literals(literal)
        if distance > len(out): raise FormatError('Referência RefPack inválida.')
        for _ in range(count): out.append(out[-distance])
        if len(out)>size: raise FormatError('RefPack excedeu o tamanho declarado.')
    if len(out)!=size: raise FormatError('Tamanho RefPack inconsistente.')
    return bytes(out)

def literal_refpack(data: bytes) -> bytes:
    """Valid literal-only stream. Avoids any lossy or proprietary compressor."""
    large=len(data)>0xFFFFFF
    out=bytearray([0x90 if large else 0x10,0xFB])
    out.extend(len(data).to_bytes(4 if large else 3,'big'))
    p=0
    while len(data)-p >= 4:
        count=min(112,((len(data)-p)//4)*4)
        out.append(0xE0+count//4-1); out.extend(data[p:p+count]); p+=count
    out.append(0xFC+len(data)-p); out.extend(data[p:])
    return bytes(out)

@dataclass
class Entry:
    name: str
    offset: int
    length: int
    index_offset: int
    original: bytes
    data: bytearray
    compressed: bool

class BigFile:
    def __init__(self, path):
        self.path=Path(path)
        self.disk_original=self.path.read_bytes()
        self.fingerprint=hashlib.sha256(self.disk_original).hexdigest()
        self.original,self.wrapper=chunk_unwrap(self.disk_original)
        d=self.original
        if d[:4] not in (b'BIG4',b'BIGF') or len(d)<16:
            raise FormatError('Este arquivo não é um BIG4/BIGF suportado.')
        count,header=struct.unpack_from('>II',d,8)
        if not 0<count<100000 or not 16<=header<=len(d):
            raise FormatError('Índice BIG inválido.')
        declared_le=struct.unpack_from('<I',d,4)[0]
        declared_be=struct.unpack_from('>I',d,4)[0]
        self.size_endian='<' if declared_le==len(d) or declared_be!=len(d) else '>'
        self.declared_size=declared_le if self.size_endian=='<' else declared_be
        self.entries={}; p=16
        for _ in range(count):
            if p+8>header: raise FormatError('Índice BIG truncado.')
            index=p; offset,length=struct.unpack_from('>II',d,p); p+=8
            end=d.find(b'\0',p,header)
            if end<0 or offset+length>len(d): raise FormatError('Entrada BIG inválida.')
            name=d[p:end].decode('latin1'); p=end+1
            if name in self.entries: raise FormatError('Entradas BIG duplicadas.')
            raw=d[offset:offset+length]
            decoded=refpack(raw)
            self.entries[name]=Entry(name,offset,length,index,decoded,bytearray(decoded),decoded!=raw)

    @property
    def dirty(self):
        return any(bytes(e.data)!=e.original for e in self.entries.values())

    def build(self):
        if not self.dirty: return self.disk_original
        out=bytearray(self.original)
        for e in self.entries.values():
            if bytes(e.data)==e.original: continue
            if e.original.startswith(b'DDS '):
                from texture_ops import validate_texture
                validate_texture(bytes(e.data))
            if len(e.data)!=len(e.original) and not e.original.startswith(b'DDS '): raise FormatError('Somente texturas DDS podem mudar de tamanho nesta versão.')
            raw=literal_refpack(bytes(e.data)) if e.compressed else bytes(e.data)
            if len(raw)<=e.length:
                out[e.offset:e.offset+len(raw)]=raw
                struct.pack_into('>I',out,e.index_offset+4,len(raw))
            else:
                # Append changed compressed entries, leaving every original region intact.
                pad=(-len(out))%64; out.extend(b'\0'*pad)
                new_offset=len(out); struct.pack_into('>II',out,e.index_offset,new_offset,len(raw)); out.extend(raw)
                for alias in self.entries.values():
                    if alias.length==0 and alias.offset==e.offset: struct.pack_into('>I',out,alias.index_offset,new_offset)
        if len(out)!=len(self.original): struct.pack_into(self.size_endian+'I',out,4,self.declared_size+len(out)-len(self.original))
        return chunk_wrap(bytes(out),self.wrapper) if self.wrapper else bytes(out)

    def save(self, path):
        path=Path(path)
        if path.resolve()==self.path.resolve() and path.exists():
            if hashlib.sha256(path.read_bytes()).hexdigest()!=self.fingerprint:
                raise FormatError('O arquivo mudou em outro programa. Recarregue antes de salvar.')
        content=self.build()
        if path.exists():
            backup=path.with_name(path.name+'.bak-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
            backup.write_bytes(path.read_bytes())
        path.parent.mkdir(parents=True,exist_ok=True)
        fd,tmp=tempfile.mkstemp(prefix=path.name+'.',suffix='.tmp',dir=path.parent)
        try:
            with os.fdopen(fd,'wb') as f: f.write(content); f.flush(); os.fsync(f.fileno())
            check=BigFile(tmp)
            for name,e in self.entries.items():
                if bytes(check.entries[name].data)!=bytes(e.data): raise FormatError('Verificação do BIG salvo falhou.')
            os.replace(tmp,path)
        finally:
            if os.path.exists(tmp): os.unlink(tmp)
        return path

class Reader:
    def __init__(self,data,pos=0,ptr=8): self.data,self.pos,self.width=data,pos,ptr
    def read(self,fmt):
        n=struct.calcsize('<'+fmt)
        if not 0<=self.pos<=len(self.data)-n: raise FormatError(f'APT truncado em 0x{self.pos:X}.')
        value=struct.unpack_from('<'+fmt,self.data,self.pos); self.pos+=n
        return value[0] if len(value)==1 else value
    def i(self): return self.read('i')
    def u(self): return self.read('I')
    def f(self): return self.read('f')
    def align(self): self.pos=(self.pos+self.width-1)//self.width*self.width
    def ptr(self): self.align(); return self.read('Q' if self.width==8 else 'I')
    def string(self,p):
        if p==0: return ''
        if not 0<=p<len(self.data): raise FormatError('Ponteiro de texto APT inválido.')
        e=self.data.find(b'\0',p)
        if e<0: raise FormatError('Texto APT sem terminador.')
        return self.data[p:e].decode('latin1')
    def text(self): return self.string(self.ptr())

IDENTITY=(1.,0.,0.,1.,0.,0.)
def multiply(a,b):
    aa,ab,ac,ad,ax,ay=a; ba,bb,bc,bd,bx,by=b
    return (aa*ba+ac*bb,ab*ba+ad*bb,aa*bc+ac*bd,ab*bc+ad*bd,aa*bx+ac*by+ax,ab*bx+ad*by+ay)
def transform(m,x,y): return (m[0]*x+m[2]*y+m[4],m[1]*x+m[3]*y+m[5])

@dataclass
class Placement:
    offset: int
    flags: int
    depth: int
    character: int
    matrix_offset: int
    matrix: tuple
    name: str
    color: int
    clip_depth: int=0
    bias: int=0

@dataclass
class Character:
    id: int
    offset: int
    type: int
    bounds: tuple=(0,0,0,0)
    texture: int=0
    frames: list=field(default_factory=list)
    text: str=''
    variable: str=''
    color: int=0xFFFFFFFF
    font_size: float=24
    font_offset: int=0
    color_offset: int=0
    alignment: int=0
    font_id: int=0

class AptFile:
    def __init__(self,big:BigFile):
        self.big=big
        self.entry=next((e for e in big.entries.values() if e.data[:8] in (b'Apt Data',b'\xb1pt Data')),None)
        if self.entry is None: raise FormatError('BIG sem recurso APT.')
        self.data=self.entry.data
        self.modified_signature=self.data[0]!=0x41
        self.width=8 if self.data[13:14]==b'8' else 4
        self.decoupled=self.data[9:10]==b'1'
        const=next((e for e in big.entries.values() if e.data[:4]==b'Apt1' or e.data[:17]==b'Apt constant file'),None)
        if const is None: raise FormatError('BIG sem constantes APT.')
        r=Reader(const.data,20,self.width); root=r.ptr()
        r,t=self.header(root)
        if t!=9: raise FormatError('Raiz APT inválida.')
        nf=r.i(); frames=r.ptr(); r.ptr(); nc=r.i(); chars=r.ptr()
        self.stage_width=r.u(); self.stage_height=r.u(); self.ms_per_frame=r.u()
        ni=r.i(); imports=r.ptr(); ne=r.i(); exports=r.ptr()
        self.root_frames=self.frames(frames,nf)
        self.characters={}; cr=Reader(self.data,chars,self.width)
        for i in range(nc):
            off=cr.ptr()
            if off and off!=root: self.characters[i]=self.character(off,i)
        self.imports={}; ir=Reader(self.data,imports,self.width)
        for _ in range(ni):
            ir.align(); movie,name=ir.text(),ir.text(); cid=ir.i(); ir.ptr()
            self.imports[cid]=(movie,name)
        self.exports={}; er=Reader(self.data,exports,self.width)
        for _ in range(ne):
            er.align(); name=er.text(); self.exports[name]=er.i()

    def header(self,off):
        r=Reader(self.data,off,self.width); t=r.i(); r.ptr()
        if self.decoupled: r.u(); r.ptr()
        return r,t

    def character(self,off,cid):
        r,t=self.header(off); c=Character(cid,off,t)
        if t in (1,2,10):
            c.bounds=r.read('4f')
            if self.decoupled: c.texture=(struct.unpack_from('<I',self.data,off+2*self.width)[0]>>16)+1
        if t==2:
            c.font_id=r.i(); c.alignment=r.i(); c.color_offset=r.pos; c.color=r.u()
            c.font_offset=r.pos; c.font_size=r.f(); r.i(); r.i(); r.i()
            c.text=r.text(); c.variable=r.text()
        elif t==3: c.text=r.text()
        elif t==5:
            count=r.i(); frames=r.ptr(); c.frames=self.frames(frames,count)
        return c

    def frames(self,off,count):
        if not 0<=count<=10000: raise FormatError('Quantidade de quadros APT inválida.')
        frames=[]; fr=Reader(self.data,off,self.width)
        for _ in range(count):
            fr.align(); n=fr.i(); p=fr.ptr(); controls=[]
            if not 0<=n<=10000: raise FormatError('Controles APT inválidos.')
            cr=Reader(self.data,p,self.width)
            for _ in range(n):
                q=cr.ptr(); r=Reader(self.data,q,self.width); t=r.i(); r.align()
                if t in (3,9):
                    flags,depth,cid=r.i(),r.i(),r.i(); mo=r.pos
                    # The on-disk matrix order is a,b,c,d,tx,ty.
                    m=r.read('6f'); scale=r.u(); bias=r.u(); r.f(); name=r.text(); clip=r.i()
                    controls.append(Placement(q,flags,depth,cid,mo,m,name,scale,clip,bias))
                elif t==4: controls.append(('remove',r.i()))
                elif t==2: controls.append(('label',r.text()))
                elif t==1: controls.append(('action',r.ptr()))
                elif t==8: controls.append(('init',r.i(),r.ptr()))
            frames.append(controls)
        return frames

    def display(self,frames,frame):
        placed={}
        for controls in frames[:min(frame+1,len(frames))]:
            for c in controls:
                if isinstance(c,Placement):
                    old=placed.get(c.depth)
                    if c.flags&2:
                        previous=old if c.flags&1 else None
                        placed[c.depth]=Placement(c.offset,c.flags,c.depth,c.character,c.matrix_offset if c.flags&4 else (previous.matrix_offset if previous else c.matrix_offset),c.matrix if c.flags&4 else (previous.matrix if previous else IDENTITY),c.name or (previous.name if previous else ''),c.color if c.flags&8 else (previous.color if previous else 0xFFFFFFFF),c.clip_depth if c.flags&64 else (previous.clip_depth if previous else -1),c.bias if c.flags&8 else (previous.bias if previous else 0))
                    elif old is not None:
                        placed[c.depth]=Placement(c.offset,c.flags,c.depth,old.character,c.matrix_offset if c.flags&4 else old.matrix_offset,c.matrix if c.flags&4 else old.matrix,c.name or old.name,c.color if c.flags&8 else old.color,c.clip_depth if c.flags&64 else old.clip_depth,c.bias if c.flags&8 else old.bias)
                elif c[0]=='remove': placed.pop(c[1],None)
        return [placed[k] for k in sorted(placed)]

    def texture(self,cid):
        e=self.big.entries.get(str(cid))
        if e is not None and e.data[:4]==b'DDS ':
            try:
                image=Image.open(io.BytesIO(e.data)); image.load(); return image.convert('RGBA')
            except (OSError,ValueError): return None
        return None

    def geometry(self,cid):
        """FIFA's GEO entry follows its shape id (0/1 are APT/CONST)."""
        e=self.big.entries.get(str(cid+1))
        if not e or len(e.data)<16 or e.data[:4]==b'DDS ': return []
        d=e.data; size,count=struct.unpack_from('<II',d)
        if size!=len(d) or not 0<count<10000 or 12+4*count>len(d): return []
        parts=[]
        for q in struct.unpack_from('<'+'I'*count,d,12):
            if q+80>len(d): continue
            length,kind=struct.unpack_from('<II',d,q)
            if kind!=1 or q+length>len(d): continue
            color,tex=struct.unpack_from('<II',d,q+32)
            mapping=struct.unpack_from('<6f',d,q+48)
            command,header=struct.unpack_from('<II',d,q+72)
            start=q+80+header-64
            if command!=2 or header not in (64,68,72,76,80) or start>q+length: continue
            if (q+length-start)%32: continue
            vertices=[struct.unpack_from('<2f',d,p) for p in range(start,q+length,32)]
            if len(vertices)<3 or len(vertices)%3 or not all(math.isfinite(v) and abs(v)<1e7 for xy in vertices for v in xy): continue
            parts.append((tex+1,color,mapping,vertices))
        return parts
