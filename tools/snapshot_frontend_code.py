"""Read only the loaded game's code and constant tables for offline analysis."""
import ctypes
import json
import struct
import sys
import time
from pathlib import Path
import psutil
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from server16_py.memory_access import Memory

OUT=Path(r'C:\Users\igorv\AppData\Local\Temp\server16_frontend_research')

def main():
    end=time.monotonic()+50
    while time.monotonic()<end:
        process=next((p for p in psutil.process_iter(['name','exe']) if (p.info['name'] or '').lower()=='fifa16.exe'),None)
        if process:
            memory=Memory();memory.process_id=process.pid
            memory.process_handle=memory.kernel32.OpenProcess(0x410,False,process.pid)
            try:
                memory.base_module=memory._get_base_address(process.info['exe'])
                if memory.read_process_memory(memory.base_module+0x435e8c0,4)==bytes.fromhex('55535648'):
                    break
            except (OSError,RuntimeError):pass
            memory.close()
        time.sleep(1)
    else:
        print('Game not ready for code snapshot');return
    OUT.mkdir(exist_ok=True)
    path=OUT/'code-and-constants.bin';ranges=[]
    try:
        with path.open('wb') as output:
            output.truncate(0x6000000)
            for start,end in [(0,0x1000),(0x2100000,0x328d000),(0x383a000,0x39eb000),(0x39fc000,0x6000000)]:
                for rva in range(start,end,0x10000):
                    try:data=memory.read_process_memory(memory.base_module+rva,min(0x10000,end-rva))
                    except RuntimeError:continue
                    output.seek(rva);output.write(data);ranges.append([rva,len(data)])
        (OUT/'snapshot.json').write_text(json.dumps({'pid':process.pid,'base':memory.base_module,'read_only':True,'ranges':ranges}),encoding='utf8')
        print(json.dumps({'snapshot':str(path),'pid':process.pid,'bytes_read':sum(x[1] for x in ranges),'read_only':True}))
    finally:memory.close()

if __name__=='__main__':main()
