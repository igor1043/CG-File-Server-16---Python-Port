"""Bounded decoder for APT ActionScript metadata. No host code is executed."""
from dataclasses import dataclass,field
import struct
from formats import Reader,FormatError

@dataclass(frozen=True)
class NumberSource:
    """Writable numeric operand in an APT action or its constant resource."""
    entry:object
    offset:int
    format:str

    @property
    def size(self):return struct.calcsize('<'+self.format)

    def encode(self,value):
        if self.format!='f':
            if not float(value).is_integer():raise ValueError('Este modelo usa uma escala inteira. Informe um número sem casas decimais.')
            value=int(value)
        return struct.pack('<'+self.format,value)

@dataclass(frozen=True)
class ScaleExpressionSource(NumberSource):
    """An eight-byte game.globalClasses.StyleManager.SCALE_FULL read.

    A local float literal occupies five bytes. Dup/Pop/ToNumber preserve its
    value and the expression's original size, so no branch or function offset
    needs relocating. This changes this request, not the global StyleManager.
    """
    @property
    def size(self):return 8

    def encode(self,value):return bytes([180])+struct.pack('<f',value)+bytes([76,23,74])

class SourceFloat(float):pass
class SourceInt(int):pass

def source_number(value,source):
    result=(SourceFloat if isinstance(value,float) else SourceInt)(value)
    result.source=source
    return result

@dataclass(frozen=True)
class RegisterValue:
    index:int

@dataclass(frozen=True)
class LookupValue:
    index:int

@dataclass
class Instruction:
    offset:int
    end:int
    op:int
    value:object=None
    body:list=field(default_factory=list)
    number_source:object=None

NAMES={0:'End',4:'NextFrame',6:'Play',7:'Stop',10:'Add',11:'Subtract',12:'Multiply',13:'Divide',14:'Equals',15:'Less',16:'And',17:'Or',18:'Not',23:'Pop',24:'Integer',28:'GetVar',29:'SetVar',33:'Concat',34:'GetProperty',35:'SetProperty',38:'Trace',48:'Random',58:'Delete',60:'Local',61:'CallFunction',62:'Return',63:'Mod',64:'New',65:'Local2',66:'Array',67:'Object',68:'TypeOf',71:'Add2',72:'Less2',73:'Equals2',74:'Number',75:'String',76:'Dup',77:'Swap',78:'GetMember',79:'SetMember',80:'Inc',81:'Dec',82:'CallMethod',83:'NewMethod',86:'This',88:'Global',89:'Zero',90:'One',91:'CallPop',92:'CallSet',93:'MethodPop',94:'MethodSet',96:'BitAnd',97:'BitOr',102:'StrictEquals',103:'Greater',105:'Extends',112:'ThisVar',113:'GlobalVar',114:'ZeroSet',115:'True',116:'False',117:'Null',118:'Undefined',129:'GotoFrame',135:'StoreReg',136:'Dictionary',139:'Target',140:'Label',142:'Function2',150:'Push',153:'Branch',155:'Function',157:'If',159:'GotoFrame2',161:'String',162:'Const',163:'Const16',164:'GetVarString',165:'GetMemberString',166:'SetVarString',167:'SetMemberString',174:'GetVarConst',175:'GetMemberConst',176:'CallConstPop',177:'CallConstSet',178:'MethodConstPop',179:'MethodConstSet',180:'Float',181:'Byte',182:'Word',183:'DWord',184:'IfFalse',185:'Register'}

class Actions:
    def __init__(self,apt):
        self.apt=apt;self.constants=[];self.functions=[];self.errors=[];self.cache={}
        entry=next((e for e in apt.big.entries.values() if e.data[:4]==b'Apt1' or e.data[:17]==b'Apt constant file'),None)
        if entry is None:return
        r=Reader(entry.data,20,apt.width);r.ptr();count=r.i();table=r.ptr();r.pos=table
        if not 0<=count<100000:raise FormatError('Constantes APT inválidas.')
        for _ in range(count):
            r.align();kind=r.i();r.align();offset=r.pos;value=r.ptr()
            if kind==1:value=r.string(value)
            elif kind==3:value=None
            elif kind==4:value=RegisterValue(value)
            elif kind==5:value=bool(value)
            elif kind in (6,7):
                fmt='f' if kind==6 else 'i'
                value=source_number(struct.unpack_from('<'+fmt,r.data,offset)[0],NumberSource(entry,offset,fmt))
            elif kind==8:value=LookupValue(value)
            self.constants.append(value)

    def pool(self,r):
        r.align();count=r.i();pointer=r.ptr();items=Reader(r.data,pointer,r.width)
        if not 0<=count<=100000:raise FormatError('Dicionário APT inválido.')
        return [self.constants[items.ptr()] for _ in range(count)]

    def decode(self,offset,end=None,pool=None,depth=0):
        if depth>32:raise FormatError('Funções APT muito profundas.')
        r=Reader(self.apt.data,offset,self.apt.width);instructions=[];pool=self.constants if pool is None else pool
        for _ in range(100000):
            if end is not None and r.pos>=end:break
            start=r.pos;op=r.read('B');value=None;body=[]
            if op in (129,135,159):r.align();value=r.i()
            elif op in (139,140,161,164,165,166,167):r.align();value=r.text()
            elif op in (136,150):
                value=self.pool(r)
                if op==136:pool=value
                else:value=[pool[item.index] if isinstance(item,LookupValue) and item.index<len(pool) else item for item in value]
            elif op in (162,174,175,176,177,178,179):
                index=r.read('B');value=pool[index] if index<len(pool) else f'?{index}'
            elif op==163:
                index=r.read('H');value=pool[index] if index<len(pool) else f'?{index}'
            elif op in (180,181,182,183,185):
                fmt={180:'f',181:'B',182:'H',183:'i',185:'B'}[op];operand=r.pos;value=r.read(fmt)
                if op!=185:
                    source=NumberSource(self.apt.entry,operand,{181:'b',182:'h'}.get(op,fmt))
                    if op==180 and bytes(r.data[r.pos:r.pos+3])==bytes([76,23,74]):source=ScaleExpressionSource(self.apt.entry,start,'f')
                    value=source_number(value,source)
            elif op in (153,157,184):r.align();delta=r.i();value=r.pos+delta
            elif op in (142,155):
                r.align();name=r.text();r.pos=(r.pos+3)//4*4;count=r.i();registers=flags=0
                if op==142:registers=r.read('h');flags=r.read('H')
                pointer=r.ptr();params=[];pr=Reader(r.data,pointer,r.width)
                if not 0<=count<10000:raise FormatError('Parâmetros APT inválidos.')
                for _ in range(count):
                    if op==142:pr.align();register=pr.u()
                    else:register=0
                    params.append((register,pr.text()))
                r.pos=(r.pos+3)//4*4;size=r.i();r.align();r.i();r.ptr()
                if size<0 or r.pos+size>len(r.data):raise FormatError('Função APT truncada.')
                body_start=r.pos;body_end=r.pos+size
                body=self.decode(body_start,body_end,pool,depth+1);r.pos=body_end
                value={'name':name,'params':params,'flags':flags,'registers':registers,'start':body_start}
                self.functions.append((value,body))
            elif op==154:pass # Native URL action; decoded for metadata only.
            elif op>=128 or op in (119,):
                raise FormatError(f'Instrução APT não suportada: {op:02X}, offset {start:X}')
            instruction=Instruction(start,r.pos,op,value,body)
            if op==175 and value=='SCALE_FULL' and len(instructions)>=3:
                chain=instructions[-3:]
                if [(i.op,i.value) for i in chain]==[(174,'game'),(175,'globalClasses'),(175,'StyleManager')] and [i.end-i.offset for i in chain]==[2,2,2] and chain[0].offset+8==r.pos:
                    instruction.number_source=ScaleExpressionSource(self.apt.entry,chain[0].offset,'f')
            instructions.append(instruction)
            if op==0 and end is None:break
        else:raise FormatError('Limite de instruções APT.')
        return instructions

    def read_all(self):
        seen=set()
        for frames in [self.apt.root_frames]+[c.frames for c in self.apt.characters.values() if c.type==5]:
            for controls in frames:
                for control in controls:
                    if isinstance(control,tuple) and control[0] in ('action','init'):
                        offset=control[-1]
                        if not offset or offset in seen:continue
                        seen.add(offset)
                        try:self.cache[offset]=self.decode(offset)
                        except (FormatError,IndexError,struct.error) as e:self.errors.append(str(e))
        return self

def listing(instructions,indent=''):
    lines=[]
    for i in instructions:
        lines.append(f'{indent}{i.offset:06X} {NAMES.get(i.op,hex(i.op))} {i.value!r}')
        if i.body:lines.extend(listing(i.body,indent+'  '))
    return lines
