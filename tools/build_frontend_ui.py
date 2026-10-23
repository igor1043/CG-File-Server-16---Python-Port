"""Append narrowly scoped APT wrappers, preserving original UI methods."""
import argparse
import json
import struct
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tools/apt_vendor')]
from formats import AptFile,BigFile
from apt_actions import Actions


class Assembler:
    def __init__(self,data):self.data=data;self.labels={};self.fixups=[]
    def align(self):self.data.extend(bytes((-len(self.data))%8))
    def op(self,value):self.data.append(value)
    def reg(self,n):self.data.extend(bytes((185,n)))
    def string(self,value):
        self.op(161);self.align();at=len(self.data);self.data.extend(bytes(8));self.fixups.append(('string',at,value))
    def member(self,name):self.string(name);self.op(78)
    def method(self,name):self.string(name);self.op(82)
    def number(self,n):
        if -128<=n<=127:self.data.extend(bytes((181,n&255)))
        else:self.op(183);self.data.extend(struct.pack('<i',n))
    def save(self,n):self.op(135);self.align();self.data.extend(struct.pack('<i',n));self.op(23)
    def field(self,name,member):self.reg(1);self.member('mcTextGroup');self.member(name);self.member(member)
    def target(self,name,member):self.reg(1);self.member('mcTextGroup');self.member(name);self.string(member)
    def branch(self,label,conditional=False):
        self.op(157 if conditional else 153);self.align();at=len(self.data);self.data.extend(bytes(4));self.fixups.append(('branch',at,label))
    def label(self,name):self.labels[name]=len(self.data)
    def path(self,*parts):
        self.string(parts[0]);self.op(28)
        for part in parts[1:]:self.member(part)
    def prop(self,parts,name,value):
        self.reg(1)
        for part in parts:self.member(part)
        self.string(name)
        if isinstance(value,bool):self.op(115 if value else 116)
        elif isinstance(value,int):self.reg(value)
        else:self.string(value)
        self.op(79)
    def finish(self):
        strings={}
        for kind,at,value in self.fixups:
            if kind=='branch':struct.pack_into('<i',self.data,at,self.labels[value]-at-4)
            else:
                if value not in strings:
                    strings[value]=len(self.data);self.data.extend(value.encode('utf8')+b'\0')
                struct.pack_into('<Q',self.data,at,strings[value])


def wrapper(asm,parts,method,saved,body):
    # Save the original method on its prototype, then install a one-argument wrapper.
    asm.path(*parts);asm.string(saved);asm.path(*parts);asm.member(method);asm.op(79)
    asm.path(*parts);asm.string(method)
    asm.op(142);asm.align();asm.data.extend(bytes(8));asm.data.extend(struct.pack('<IHH',1,5,41))
    param_at=len(asm.data);asm.data.extend(bytes(8));size_at=len(asm.data);asm.data.extend(bytes(4));asm.align()
    asm.data.extend(struct.pack('<I',0x98765432));asm.align();asm.data.extend(struct.pack('<Q',0x12345678))
    start=len(asm.data);body(asm);struct.pack_into('<I',asm.data,size_at,len(asm.data)-start);asm.op(79)
    return param_at


def background_body(a):
    a.reg(2);a.string('server16_frontend_clear');a.op(73);a.branch('show',True)
    # Ordinary images keep the original loading and completion behavior.
    a.prop(['mcImage'],'_visible',True)
    a.reg(2);a.number(1);a.reg(1);a.method('Server16OriginalLoadImage');a.op(62)
    a.label('show');a.prop(['mcImage'],'_visible',False)
    a.prop([],'m_strImageId',2);a.prop([],'m_isLoaded',True)
    a.op(89);a.reg(1);a.method('LoadImageComplete');a.op(23)
    a.op(115);a.op(62)


def panorama_body(a):
    a.reg(2);a.number(1);a.reg(1);a.method('Server16OriginalUpdate');a.op(23)
    a.op(89);a.reg(2);a.method('GetStadiumCapacity');a.number(0);a.op(103);a.save(3)
    a.op(89);a.reg(2);a.method('GetStadiumYearBuilt');a.save(4)
    a.reg(4);a.number(0);a.op(103);a.save(6)
    a.reg(4);a.number(9999999);a.op(103);a.branch('custom',True)
    a.branch('visibility')
    a.label('custom')
    a.reg(4);a.number(10000001);a.op(11);a.save(5)
    a.reg(5);a.number(0);a.op(72);a.op(18);a.save(6)
    a.prop(['mcTextGroup','mYearName'],'text','PÚBLICO')
    a.target('mYearValue','text');a.reg(5);a.number(1);a.path('cafe','ION_Localization');a.method('LocalizeInteger');a.op(79)
    # Recompute widths after replacing FIFA's construction year with attendance.
    for name in ('mYearName','mYearValue'):
        a.target(name,'_x');a.number(0);a.field(name,'textWidth');a.op(11);a.number(10);a.op(11);a.op(79)
    a.field('mYearName','_x');a.field('mYearValue','_x');a.op(72);a.branch('nameLeft',True)
    a.field('mYearValue','_x');a.save(7);a.branch('leftReady')
    a.label('nameLeft');a.field('mYearName','_x');a.save(7)
    a.label('leftReady');a.reg(6);a.branch('hasYear',True)
    a.number(0);a.save(7)
    a.label('hasYear')
    for name in ('mCapacityName','mCapacityValue'):
        a.target(name,'_x');a.reg(7);a.field(name,'textWidth');a.op(11);a.number(24);a.op(11);a.op(79)
    a.target('mcDivderBottomVertical','_x');a.reg(7);a.number(12);a.op(11);a.op(79)
    a.label('visibility')
    for name in ('mCapacityName','mCapacityValue'):
        a.prop(['mcTextGroup',name],'_visible',3)
    for name in ('mYearName','mYearValue'):
        a.prop(['mcTextGroup',name],'_visible',6)
    a.reg(3);a.reg(6);a.op(16);a.save(8)
    a.prop(['mcTextGroup','mcDivderBottomVertical'],'_visible',8)
    a.op(118);a.op(62)


def build(source,out,kind):
    big=BigFile(source);apt=AptFile(big);actions=Actions(apt).read_all()
    if actions.errors:raise ValueError(actions.errors)
    start,block=next((s,b) for s,b in actions.cache.items() if b[0].op==136)
    if block[-1].op!=0:raise ValueError('Missing root End')
    data=apt.entry.data;original=bytes(data[start:block[-1].offset]);a=Assembler(data);a.align();new_start=len(data);data.extend(original)
    parts=('game','background','BackgroundFIFA','prototype') if kind=='background' else ('game','screens','misc','StadiumPan','prototype')
    method='LoadImage' if kind=='background' else 'Update'
    param_at=wrapper(a,parts,method,'Server16Original'+method,background_body if kind=='background' else panorama_body)
    a.op(0);a.align();param=len(data);data.extend(struct.pack('<I',2));a.align();name_at=len(data);data.extend(bytes(8))
    a.fixups.append(('string',name_at,'server16Argument'));struct.pack_into('<Q',data,param_at,param)
    # Only the root control's action pointer is redirected. All original strings,
    # constants, characters, textures and method bodies remain byte-identical.
    signature=struct.pack('<Q',start);refs=[]
    for at in range(0,len(apt.entry.original)-7,8):
        if apt.entry.original[at:at+8]==signature:refs.append(at)
    if len(refs)!=1:raise ValueError(f'Ambiguous root action references: {refs}')
    struct.pack_into('<Q',data,refs[0],new_start);a.finish()
    # ScoreboardStudio's conservative writer forbids larger APTs. Rebuild the
    # enclosing BIG directory while retaining every other decoded entry.
    entries=[(e.name,bytes(e.data)) for e in big.entries.values()]
    header=16+sum(8+len(n.encode('latin1'))+1 for n,d in entries);offset=(header+63)//64*64
    directory=bytearray();payload=bytearray(bytes(offset-header))
    for name,blob in entries:
        directory.extend(struct.pack('>II',offset,len(blob))+name.encode('latin1')+b'\0');payload.extend(blob);offset+=len(blob)
    output=b'BIGF'+struct.pack('<I',offset)+struct.pack('>II',len(entries),header)+directory+payload
    out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(output)
    check=Actions(AptFile(BigFile(out))).read_all()
    if check.errors:raise ValueError(check.errors)
    print(json.dumps({'file':str(out),'kind':kind,'functions':len(check.functions),'root_pointer':refs[0],'bytes':len(output)}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    src=ROOT/'native_mods/frontend_stadium/ui_templates'
    for name,kind in [('backgroundfifa','background'),('stadiumpan','panorama')]:
        build(src/(name+'.big'),args.output/(name+'.big'),kind)
