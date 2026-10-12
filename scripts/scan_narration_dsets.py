"""Read-only search for relocated speech datasets, distinct from raw caches."""
import ctypes,struct,json,sys,sqlite3
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server16_py.memory_access import Memory
from server16_py.narration_bank import HarmonyBank
class MBI(ctypes.Structure):
    _fields_=[('BaseAddress',ctypes.c_void_p),('AllocationBase',ctypes.c_void_p),('AllocationProtect',ctypes.c_uint32),('PartitionId',ctypes.c_uint16),('RegionSize',ctypes.c_size_t),('State',ctypes.c_uint32),('Protect',ctypes.c_uint32),('Type',ctypes.c_uint32)]
root=Path(__file__).resolve().parents[1]
db=sqlite3.connect(root/'tools/narration_studio/catalog.sqlite')
wanted={r[0] for r in db.execute("select distinct dataset_id from clips where event='bINTRO_HELLO_SHORT'")};db.close()
m=Memory();assert m.attack('fifa16');k=m.kernel32
k.VirtualQueryEx.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.POINTER(MBI),ctypes.c_size_t];k.VirtualQueryEx.restype=ctypes.c_size_t
address=0;hits=[]
while address<0x7fffffffffff:
    info=MBI()
    if not k.VirtualQueryEx(m.process_handle,ctypes.c_void_p(address),ctypes.byref(info),ctypes.sizeof(info)):break
    start=info.BaseAddress or 0;size=info.RegionSize
    if info.State==0x1000 and not info.Protect&0x101 and info.Type==0x20000:
        for offset in range(0,size,4*1024*1024):
            try:data=m.read_process_memory(start+offset,min(size-offset,4*1024*1024+512))
            except Exception:continue
            pos=0
            while True:
                pos=data.find(b'TESD',pos)
                if pos<0:break
                if pos+72<len(data) and struct.unpack_from('<I',data,pos+8)[0] in wanted:
                    ptr=start+offset+pos
                    hit=dict(address=hex(ptr),data=data[pos:pos+256].hex(),data_pointer=hex(struct.unpack_from('<Q',data,pos+24)[0]))
                    hits.append(hit);print(hit,flush=True)
                pos+=4
    address=start+size
(root/'artifacts/narration_research/ram_intro_dsets.json').write_text(json.dumps(hits,indent=2));m.close()
