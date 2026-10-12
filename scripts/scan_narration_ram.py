"""Locate byte-identical SBR caches. No memory writes."""
import ctypes, struct, hashlib, json, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server16_py.memory_access import Memory
class MBI(ctypes.Structure):
    _fields_=[('BaseAddress',ctypes.c_void_p),('AllocationBase',ctypes.c_void_p),('AllocationProtect',ctypes.c_uint32),('PartitionId',ctypes.c_uint16),('RegionSize',ctypes.c_size_t),('State',ctypes.c_uint32),('Protect',ctypes.c_uint32),('Type',ctypes.c_uint32)]
m=Memory(); assert m.attack('fifa16')
k=m.kernel32
k.VirtualQueryEx.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.POINTER(MBI),ctypes.c_size_t]
k.VirtualQueryEx.restype=ctypes.c_size_t
out=Path(__file__).resolve().parents[1]/'artifacts/narration_research'
expected={hashlib.sha256(p.read_bytes()).hexdigest():p.name for p in (Path(__file__).resolve().parents[1]/'tools/narration_studio/banks').glob('*.sbr')}
address=0; hits=[]; scanned=0
while address<0x7fffffffffff:
    info=MBI()
    if not k.VirtualQueryEx(m.process_handle,ctypes.c_void_p(address),ctypes.byref(info),ctypes.sizeof(info)):break
    start=info.BaseAddress or 0; size=info.RegionSize
    if info.State==0x1000 and not(info.Protect&0x101) and info.Type==0x20000:
        for offset in range(0,size,4*1024*1024):
            try: data=m.read_process_memory(start+offset,min(size-offset,4*1024*1024+512))
            except Exception:continue
            scanned+=len(data); pos=0
            while True:
                pos=data.find(b'SBle',pos)
                if pos<0:break
                if pos+40<=len(data):
                    length=struct.unpack_from('<I',data,pos+4)[0]
                    if 80<=length<=1024*1024:
                        try:
                            bank=m.read_process_memory(start+offset+pos,length)
                            sha=hashlib.sha256(bank).hexdigest()
                            if sha in expected:
                                hit=dict(address=hex(start+offset+pos),size=length,bank=expected[sha],sha256=sha)
                                hits.append(hit); print(hit,flush=True)
                        except Exception:pass
                pos+=4
    address=start+size
(out/'ram_sbr_caches.json').write_text(json.dumps(dict(pid=m.process_id,bytes_scanned=scanned,caches=hits),indent=2))
print('SCANNED',scanned,'CACHES',len(hits));m.close()
