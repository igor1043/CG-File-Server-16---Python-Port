"""Read-only, bounded native job-offer disassembly for the installed FIFA build."""
import bisect
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import re
import struct
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'runtime/dev_deps'))


def main():
    import pefile,psutil
    from capstone import Cs,CS_ARCH_X86,CS_MODE_64
    from server16_py.memory_access import Memory
    proc=next(p for p in psutil.process_iter(['name','exe']) if (p.info['name'] or '').lower()=='fifa16.exe')
    path=Path(proc.info['exe']);raw=path.read_bytes();pe=pefile.PE(str(path),fast_load=True)
    labels=['JobOfferManager','JobOffersGenerated','JobOfferManager::InformOfJobOffer',
            'JobOfferManager::DeclineJobApplication','**JobOfferManager - Added offer']
    targets={}
    for label in labels:
        needle=label.encode()+ (b'\0' if label!='**JobOfferManager - Added offer' else b'')
        for found in re.finditer(re.escape(needle),raw):
            targets[pe.get_rva_from_offset(found.start())]=label
    pdata=next(s for s in pe.sections if s.Name.startswith(b'.pdata')).get_data()
    functions=sorted((a,b) for a,b,_ in struct.iter_unpack('<III',pdata[:len(pdata)//12*12])
                     if 0<a<b<pe.OPTIONAL_HEADER.SizeOfImage)
    starts=[a for a,b in functions]
    memory=Memory();memory.process_id=proc.pid
    memory.process_handle=memory.kernel32.OpenProcess(0x410,False,proc.pid)
    memory.base_module=memory._get_base_address(str(path))
    class Region(ctypes.Structure):
        _fields_=[('base',ctypes.c_void_p),('allocation',ctypes.c_void_p),('allocation_protect',wintypes.DWORD),
                  ('partition',wintypes.WORD),('size',ctypes.c_size_t),('state',wintypes.DWORD),
                  ('protect',wintypes.DWORD),('type',wintypes.DWORD)]
    query=memory.kernel32.VirtualQueryEx
    query.argtypes=[wintypes.HANDLE,ctypes.c_void_p,ctypes.POINTER(Region),ctypes.c_size_t]
    query.restype=ctypes.c_size_t
    cursor=memory.base_module;limit=cursor+pe.OPTIONAL_HEADER.SizeOfImage
    refs=[];pattern=re.compile(b'[\x48\x4c]\x8d[\x05\x0d\x15\x1d\x25\x2d\x35\x3d]....',re.S)
    while cursor<limit:
        region=Region()
        if not query(memory.process_handle,cursor,ctypes.byref(region),ctypes.sizeof(region)):break
        end=min(limit,region.base+region.size)
        if region.state==0x1000 and not region.protect&0x101:
            for address in range(cursor,end,1<<20):
                try:data=memory.read_process_memory(address,min((1<<20)+7,end-address))
                except RuntimeError:continue
                rva=address-memory.base_module
                for match in pattern.finditer(data):
                    source=rva+match.start();target=source+7+struct.unpack_from('<i',match[0],3)[0]
                    if target in targets:refs.append((source,targets[target]))
                for match in re.finditer(b'\xe8....',data,re.S):
                    source=rva+match.start()
                    if source+5+struct.unpack_from('<i',match[0],1)[0]==0x4456a60:
                        refs.append((source,'JobOfferService'))
        if end<=cursor:break
        cursor=end
    out=ROOT/'artifacts/career_jobs_disassembly';out.mkdir(exist_ok=True)
    decoder=Cs(CS_ARCH_X86,CS_MODE_64)
    decoder.skipdata=True
    results=[]
    refs.extend((int(argument,16),'manual') for argument in sys.argv[1:])
    for source,label in refs:
        index=bisect.bisect_right(starts,source)-1
        start,end=functions[index] if index>=0 else (source,source+256)
        if not start<=source<end or end-start>100000:start,end=source,source+256
        name=f'{start:08x}.asm'
        data=memory.read_process_memory(memory.base_module+start,end-start)
        (out/name).write_text('\n'.join(f'{i.address:08x} {i.mnemonic:8} {i.op_str}'
                                       for i in decoder.disasm(data,start)),encoding='utf8')
        results.append({'label':label,'xref':hex(source),'function':hex(start),'end':hex(end),'file':name})
    memory.close()
    (out/'references.json').write_text(json.dumps(results,indent=2),encoding='utf8')
    print(json.dumps(results,indent=2))


if __name__=='__main__':main()
