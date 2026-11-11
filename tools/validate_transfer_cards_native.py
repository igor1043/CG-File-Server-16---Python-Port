"""Execute the compiled card hook AND native publisher/row APIs in Unicorn.

Reads the executable and newly built DLL; never opens FIFA or alters a save.
Only engine services (allocator/storage properties, names, currency, strings)
are synthetic. Real CPU code performs capacity checks, AddRow/SelectRow,
filtering, ID/PARAM serialization and both publications into the same provider.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import sys

if os.environ.get('FIFA16_TEST_DEPS'):
    sys.path.insert(0,os.environ['FIFA16_TEST_DEPS'])
import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE, UC_HOOK_MEM_UNMAPPED
from unicorn.x86_const import (UC_X86_REG_RAX, UC_X86_REG_RCX, UC_X86_REG_RDX,
    UC_X86_REG_R8, UC_X86_REG_R9, UC_X86_REG_RSP, UC_X86_REG_RIP)

ROOT=Path(__file__).resolve().parents[1]
IMAGE=Path(os.environ.get('FIFA16_TEST_IMAGE','U:/fifa 16/fifa16.bin'))
NATIVE=ROOT/'career_native/build/production'
PE=pefile.PE(str(IMAGE),fast_load=True)
DLL=pefile.PE(str(NATIVE/'dinput8.dll'),fast_load=True)
BASE=PE.OPTIONAL_HEADER.ImageBase
DBASE=DLL.OPTIONAL_HEADER.ImageBase
SYMBOLS={m[1]:int(m[2],16) for m in re.finditer(
    r'^\s+\w+:\w+\s+(\S+)\s+([0-9a-fA-F]{16})\s',
    (NATIVE/'dinput8.map').read_text(),re.M)}
ENTRY=0x59170A0
SITES=(0x59BE962,0x59BE99B,0x59C0B48,0x59C0B81)

class Machine:
    def __init__(self):
        self.uc=Uc(UC_ARCH_X86,UC_MODE_64)
        self.stack,self.heap,self.shim=0x20000000,0x30000000,0x10002000
        self.uc.mem_map(self.stack,0x20000)
        self.uc.mem_map(self.heap,0x40000)
        self.uc.mem_map(0x10000000,0x4000)
        self.uc.mem_map(DBASE,(DLL.OPTIONAL_HEADER.SizeOfImage+4095)&~4095)
        self.uc.mem_write(DBASE,DLL.get_memory_mapped_image())
        self.mapped=set()
        self.owner=self.heap+0x1000
        registry,slot,self.service,vtable=(self.heap+0x2000,self.heap+0x3000,
                                        self.heap+0x4000,self.heap+0x5000)
        self.provider,self.storage,self.svtable,self.nodes=(self.heap+0x6000,
            self.heap+0x6100,self.heap+0x6200,self.heap+0x6300)
        self.vector,self.rows=self.heap+0x8000,self.heap+0x9000
        self.blocks=[self.heap+0x10000+i*0x200 for i in range(8)]
        self.strings=self.heap+0x18000
        self.data=[{} for _ in range(32)]
        self.capacity=6
        self.allocations=0
        self.string_cursor=0
        self.player=0
        self.selected=[]
        self.put(self.owner+8,registry)
        self.put(registry+0x18,slot);self.put(slot,self.service)
        self.put(self.service,vtable)
        for offset in (8,0x18,0x20,0x30,0x60,0xe0):
            self.put(vtable+offset,self.shim+offset)
        self.put(self.provider+0x18,self.storage)
        self.put(self.storage,self.svtable)
        self.put(self.svtable+0x18,self.shim+0x118)
        self.put(self.svtable+0x20,self.shim+0x120)
        for i,block in enumerate(self.blocks):self.put(self.nodes+i*8,block)
        self.set_capacity()
        bindings={'g_transfer_cards_publish':ENTRY,
                  'g_transfer_cards_row_count':0x5AC1E80,
                  'g_transfer_cards_add_row':0x5A2A4F0,
                  'g_transfer_cards_select_row':0x5B0EB50,
                  'g_transfer_cards_set_string':0x5A511E0}
        for name,rva in bindings.items():self.put(SYMBOLS[name],BASE+rva)
        self.uc.hook_add(UC_HOOK_MEM_UNMAPPED,self.missing)
        self.uc.hook_add(UC_HOOK_CODE,self.code)

    def put(self,address,value):self.uc.mem_write(address,struct.pack('<Q',value))
    def get(self,address):return struct.unpack('<Q',bytes(self.uc.mem_read(address,8)))[0]
    def reg(self,register):return self.uc.reg_read(register)
    def text(self,address):
        for page in (address&~4095,(address+255)&~4095):
            if BASE<=page<BASE+PE.OPTIONAL_HEADER.SizeOfImage and page not in self.mapped:
                assert self.missing(self.uc,0,page,1,0,None)
        return bytes(self.uc.mem_read(address,256)).split(b'\0')[0].decode('ascii')
    def new_string(self,text):
        raw=text.encode('ascii')+b'\0';address=self.strings+self.string_cursor
        self.string_cursor+=len(raw)+8
        assert self.string_cursor<0x20000
        self.uc.mem_write(address,raw)
        return address
    def native_string(self,address,text):
        pointer=self.new_string(text)
        self.put(address,pointer);self.put(address+8,pointer+len(text))
        self.put(address+0x10,pointer+len(text)+1)
    def set_capacity(self):
        # The real engine's 4 x 112-byte deque blocks; original GetCount and
        # SelectRow execute against this layout, including their bounds checks.
        first=self.blocks[0];last=self.blocks[self.capacity//4]
        for offset,value in ((0x18,first),(0x20,first),(0x28,first+448),
            (0x30,self.nodes),(0x38,last+(self.capacity%4)*112),
            (0x40,last),(0x48,last+448),(0x50,self.nodes+(self.capacity//4)*8)):
            self.put(self.storage+offset,value)
    def missing(self,uc,access,address,size,value,context):
        page=address&~4095
        if page in self.mapped or not BASE<=page<BASE+PE.OPTIONAL_HEADER.SizeOfImage:return False
        uc.mem_map(page,4096);self.mapped.add(page)
        raw=PE.get_data(page-BASE,4096)
        if raw:uc.mem_write(page,raw)
        return True
    def finish(self,result=0):
        sp=self.reg(UC_X86_REG_RSP);ret=self.get(sp)
        self.uc.reg_write(UC_X86_REG_RAX,result)
        self.uc.reg_write(UC_X86_REG_RSP,sp+8)
        self.uc.reg_write(UC_X86_REG_RIP,ret)
    def code(self,uc,address,size,context):
        r=address-BASE;rcx=self.reg(UC_X86_REG_RCX)
        rdx=self.reg(UC_X86_REG_RDX);r8=self.reg(UC_X86_REG_R8)
        r9=self.reg(UC_X86_REG_R9);sp=self.reg(UC_X86_REG_RSP)
        if address==SYMBOLS['snprintf']:
            value=self.text(r8) % (self.text(r9),self.get(sp+0x28)&0xffffffff)
            uc.mem_write(rcx,value.encode()+b'\0');self.finish(len(value))
        elif r in (0x425D990,0x425D9C0,0x4529C10,0x5AAFFF0):self.finish(self.service)
        elif r in (0x4457580,0x44575E0):uc.mem_write(rcx,b'\0'*4);self.finish(rcx)
        elif r==0x5AC8A90:self.finish(1)
        elif r==0x4BBDE00:self.finish(self.new_string('PLAYER '+str(self.player)))
        elif r in (0x4BBDEA0,0x3A34520):self.finish()
        elif r==0x3A34200:
            fmt=self.text(rdx)
            if fmt=='%s%d':value=fmt % (self.text(r8),r9&0xffffffff)
            else:
                assert fmt=='%d|%d|%d|%d|%s|%s'
                value=fmt % (r8&0xffffffff,r9&0xffffffff,self.get(sp+0x28)&0xffffffff,
                    self.get(sp+0x30)&0xffffffff,self.text(self.get(sp+0x38)),
                    self.text(self.get(sp+0x40)))
            self.native_string(rcx,value);self.finish()
        elif address==self.shim+0x118:
            assert rcx==self.storage
            old=self.capacity;self.capacity+=1;self.allocations+=1
            self.set_capacity();self.finish(old)
        elif address==self.shim+0x120:
            assert rcx==self.storage and 0<=rdx<self.capacity
            self.data[rdx][self.text(r8)]=self.text(r9);self.finish()
        elif self.shim<=address<self.shim+0x100:
            if address==self.shim+0x20:self.player=rdx&0xffffffff
            if address==self.shim+0xe0:self.native_string(rdx,'$'+str(r9&0xffffffff))
            self.finish(self.service if address in (self.shim+0x18,self.shim+0x30) else 0)
        elif r==0x5B0EB50:
            assert rdx<self.capacity,('native SelectRow rejected output index',rdx,self.capacity)
            self.selected.append(rdx)

    def publish(self,count,latest,invalid=()):
        self.put(self.vector+8,self.rows)
        self.put(self.vector+0x10,self.rows+count*0x70)
        for i in range(count):
            row=bytearray(0x70)
            for offset,value in ((4,1000+i+latest*100),(8,100+i),(12,200+i),
                                 (0x34,1000000+i),(0x44,3)):
                struct.pack_into('<I',row,offset,value)
            if i in invalid:row[0x6c]=1
            self.uc.mem_write(self.rows+i*0x70,bytes(row))
        sp=self.stack+0x10008;first=3 if latest else 0
        self.put(sp,0x10000000);self.put(sp+0x28,self.vector);self.put(sp+0x30,latest)
        for register,value in ((UC_X86_REG_RSP,sp),(UC_X86_REG_RCX,self.owner),
            (UC_X86_REG_RDX,self.provider),(UC_X86_REG_R8,first),(UC_X86_REG_R9,first+3)):
            self.uc.reg_write(register,value)
        self.uc.emu_start(SYMBOLS['career_transfer_cards_publish'],0x10000000,count=300000)
        assert self.reg(UC_X86_REG_RIP)==0x10000000,'Hook failed to return'
        eligible=[i for i in range(count) if i not in invalid][:10]
        start=10 if latest else 0;prefix='LASTDEAL' if latest else 'TOPDEAL'
        for j in range(10):
            row=self.data[start+j]
            assert row['ID']==prefix+str(start+j)
            assert row['VISIBLE']==('TRUE' if j<len(eligible) else 'FALSE')
            if j<len(eligible):
                i=eligible[j];values=row['PARAM'].split('|')
                assert values==list(map(str,(j,1000+i+latest*100,100+i,200+i)))+[
                    'PLAYER '+str(1000+i+latest*100),'$'+str(1000000+i)],values
        assert self.capacity==20 and self.allocations==14
        return {'source_count':count,'latest':bool(latest),'filtered':list(invalid),
                'published':len(eligible),'provider_capacity':self.capacity}


def main():
    for site in SITES:
        code=PE.get_data(site,5)
        assert code[0]==0xe8 and site+5+struct.unpack_from('<i',code,1)[0]==ENTRY
    checks=[]
    for n in (0,1,3,10,25):
        machine=Machine()
        checks.append(machine.publish(n,0));top=[dict(r) for r in machine.data[:10]]
        checks.append(machine.publish(n,1));assert machine.data[:10]==top
        # A smaller subsequent refresh clears stale rows without allocating
        # again and without disturbing the other slide.
        latest=[dict(r) for r in machine.data[10:20]]
        machine.publish(0,0);assert machine.data[10:20]==latest
        machine.publish(0,1)
    machine=Machine()
    for latest in (1,0):checks.append(machine.publish(25,latest,(0,3,7,11,14)))
    report={'passed':True,'checks':checks,'native_call_sites':[hex(s) for s in SITES],
            'installed_image_sha256':hashlib.sha256(IMAGE.read_bytes()).hexdigest(),
            'native_dll_sha256':hashlib.sha256((NATIVE/'dinput8.dll').read_bytes()).hexdigest(),
            'compiled_hook_executed':True,'native_loop_executed':True,
            'native_selector_and_row_count_executed':True,'native_param_serialization_executed':True,
            'shared_provider_no_collisions':True,'shrinking_refresh_clears_stale_rows':True,
            'engine_services_synthetic':True,'game_process_opened':False,'save_modified':False}
    path=ROOT/'artifacts/career_transfer_cards/native_emulation.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
