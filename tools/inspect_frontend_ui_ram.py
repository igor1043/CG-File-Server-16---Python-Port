"""Find loaded APT method markers in committed memory, with read-only access."""
import ctypes
import json
import sys
from ctypes import wintypes
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server16_py.memory_access import Memory

class Region(ctypes.Structure):
    _fields_=[('base',ctypes.c_uint64),('allocation',ctypes.c_uint64),('allocation_protect',wintypes.DWORD),
              ('partition',wintypes.WORD),('padding',wintypes.WORD),('size',ctypes.c_uint64),
              ('state',wintypes.DWORD),('protect',wintypes.DWORD),('kind',wintypes.DWORD),('padding2',wintypes.DWORD)]

def main():
    import psutil
    process=next(p for p in psutil.process_iter(['name']) if (p.info['name'] or '').lower()=='fifa16.exe')
    memory=Memory();memory.process_id=process.pid
    memory.process_handle=memory.kernel32.OpenProcess(0x410,False,process.pid)
    query=memory.kernel32.VirtualQueryEx
    query.argtypes=[wintypes.HANDLE,ctypes.c_void_p,ctypes.POINTER(Region),ctypes.c_size_t]
    query.restype=ctypes.c_size_t
    labels=['Server16OriginalLoadImage','Server16OriginalUpdate','BackgroundFIFA::LoadImage()',
            'server16_frontend_clear']
    needles=[(label,encoding,label.encode(encoding)) for label in labels for encoding in ('ascii','utf-16-le')]
    hits=[];total=0;address=0x10000
    try:
        while address<0x7fffffffffff and total<6*1024**3:
            region=Region()
            if not query(memory.process_handle,address,ctypes.byref(region),ctypes.sizeof(region)):break
            address=region.base+region.size
            if region.state!=0x1000 or region.protect&0x101 or not region.protect&0xee:continue
            tail=b''
            for offset in range(0,region.size,4*1024**2):
                size=min(4*1024**2,region.size-offset)
                try:raw=memory.read_process_memory(region.base+offset,size)
                except RuntimeError:tail=b'';continue
                data=tail+raw;start=region.base+offset-len(tail);total+=size
                for label,encoding,needle in needles:
                    at=data.find(needle)
                    while at>=0:
                        hits.append({'marker':label,'encoding':encoding,'address':hex(start+at),'region':hex(region.base),'kind':hex(region.kind)})
                        at=data.find(needle,at+len(needle))
                tail=data[-128:]
    finally:memory.close()
    print(json.dumps({'pid':process.pid,'ram_write_access':False,'bytes_scanned':total,'hits':hits},indent=2))

if __name__=='__main__':main()
