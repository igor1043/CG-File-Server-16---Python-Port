"""Exercise the installed native publisher in an isolated CPU emulator.

Only reads fifa16.bin. All engine services, records and output are synthetic;
does not open a process, launch FIFA, send input or modify any save/game file.
"""
import hashlib
import json
import os
from pathlib import Path
import struct
import sys

if os.environ.get('FIFA16_TEST_DEPS'):
    sys.path.insert(0,os.environ['FIFA16_TEST_DEPS'])
import pefile
from unicorn import Uc,UC_ARCH_X86,UC_MODE_64,UC_HOOK_CODE,UC_HOOK_MEM_UNMAPPED
from unicorn.x86_const import UC_X86_REG_RAX,UC_X86_REG_RCX,UC_X86_REG_RDX,UC_X86_REG_R8,UC_X86_REG_R9,UC_X86_REG_RSP,UC_X86_REG_RIP

ROOT=Path(__file__).resolve().parents[1]
IMAGE=Path('U:/fifa 16/fifa16.bin')
PE=pefile.PE(str(IMAGE),fast_load=True)
BASE=PE.OPTIONAL_HEADER.ImageBase
ENTRY=0x59170A0
SITES=(0x59BE962,0x59BE99B,0x59C0B48,0x59C0B81)


def run(count,latest,invalid=()):
    uc=Uc(UC_ARCH_X86,UC_MODE_64)
    stack,heap,shim=0x20000000,0x30000000,0x10002000
    uc.mem_map(stack,0x20000);uc.mem_map(heap,0x20000);uc.mem_map(0x10000000,0x4000)
    def put(address,value):uc.mem_write(address,struct.pack('<Q',value))
    def get(address):return struct.unpack('<Q',bytes(uc.mem_read(address,8)))[0]
    owner,registry,slot,service,vtable=heap+0x1000,heap+0x2000,heap+0x3000,heap+0x4000,heap+0x5000
    vector,rows=heap+0x8000,heap+0x9000
    put(owner+8,registry);put(registry+0x18,slot);put(slot,service);put(service,vtable)
    for offset in (8,0x18,0x20,0x30,0x60,0xe0):put(vtable+offset,shim+offset)
    put(vector+8,rows);put(vector+0x10,rows+count*0x70)
    for i in range(count):
        row=bytearray(0x70)
        for offset,value in ((4,1000+i),(8,100+i),(12,200+i),(0x34,1000000+i),(0x44,3)):
            struct.pack_into('<I',row,offset,value)
        if i in invalid:row[0x6c]=1
        uc.mem_write(rows+i*0x70,bytes(row))
    captured=[];mapped=set()
    def missing(uc,access,address,size,value,context):
        page=address&~0xfff
        if page in mapped:return False
        if not BASE<=page<BASE+PE.OPTIONAL_HEADER.SizeOfImage:return False
        uc.mem_map(page,4096);mapped.add(page)
        raw=PE.get_data(page-BASE,4096)
        if raw:uc.mem_write(page,raw)
        return True
    def finish(result=0):
        sp=uc.reg_read(UC_X86_REG_RSP);ret=get(sp)
        uc.reg_write(UC_X86_REG_RAX,result);uc.reg_write(UC_X86_REG_RSP,sp+8);uc.reg_write(UC_X86_REG_RIP,ret)
    noops=(0x4BBDEA0,0x3A34520)
    def code(uc,address,size,context):
        r=address-BASE;rcx=uc.reg_read(UC_X86_REG_RCX)
        if r in (0x425D990,0x425D9C0,0x4529C10,0x5AAFFF0):finish(service)
        elif r in (0x4457580,0x44575E0):uc.mem_write(rcx,b'\0'*4);finish(rcx)
        elif r==0x5AC8A90:finish(1)
        elif r==0x4BBDE00:finish(heap+0x7000)
        elif r in noops:finish()
        elif shim<=address<shim+0x100:
            # Mock allocator, name service, formatted currency, and release.
            finish(service if address in (shim+0x18,shim+0x30) else 0)
        elif r==0x59AFD30:
            sp=uc.reg_read(UC_X86_REG_RSP)
            captured.append({'id':uc.reg_read(UC_X86_REG_R8),'offset':uc.reg_read(UC_X86_REG_R9),
                             'latest':get(sp+0x28)&0xffffffff,'player':get(sp+0x30)&0xffffffff,
                             'buying':get(sp+0x38)&0xffffffff,'selling':get(sp+0x40)&0xffffffff})
            finish()
    uc.hook_add(UC_HOOK_MEM_UNMAPPED,missing);uc.hook_add(UC_HOOK_CODE,code)
    sp=stack+0x10008;first=3 if latest else 0
    put(sp,0x10000000);put(sp+0x28,vector);put(sp+0x30,latest)
    uc.reg_write(UC_X86_REG_RSP,sp);uc.reg_write(UC_X86_REG_RCX,owner)
    uc.reg_write(UC_X86_REG_RDX,heap+0x6000);uc.reg_write(UC_X86_REG_R8,first)
    uc.reg_write(UC_X86_REG_R9,first+10)
    uc.emu_start(BASE+ENTRY,0x10000000,count=100000)
    assert uc.reg_read(UC_X86_REG_RIP)==0x10000000,'Native publisher failed to return'
    eligible=[i for i in range(count) if i not in invalid][:10]
    assert [r['id'] for r in captured]==list(range(first,first+len(eligible)))
    assert [r['offset'] for r in captured]==list(range(len(eligible)))
    assert [r['player'] for r in captured]==[1000+i for i in eligible]
    assert [r['buying'] for r in captured]==[100+i for i in eligible]
    assert [r['selling'] for r in captured]==[200+i for i in eligible]
    assert all(r['latest']==latest for r in captured)
    return {'source_count':count,'latest':bool(latest),'filtered':list(invalid),'published':len(captured)}


def main():
    for site in SITES:
        code=PE.get_data(site,5)
        assert code[0]==0xe8 and site+5+struct.unpack_from('<i',code,1)[0]==ENTRY
    checks=[run(n,latest) for n in (0,1,3,10,25) for latest in (0,1)]
    checks.extend(run(25,latest,(0,3,7,11,14)) for latest in (0,1))
    report={'passed':True,'checks':checks,'native_call_sites':[hex(s) for s in SITES],
            'installed_image_sha256':hashlib.sha256(IMAGE.read_bytes()).hexdigest(),
            'native_loop_executed':True,'engine_services_synthetic':True,
            'game_process_opened':False,'save_modified':False}
    (ROOT/'artifacts/career_transfer_cards/native_emulation.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
