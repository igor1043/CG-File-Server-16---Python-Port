from pathlib import Path
import sys,struct,psutil,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server16_py.memory_access import Memory
from capstone import Cs,CS_ARCH_X86,CS_MODE_64
m=Memory()
if not m.attack('fifa16'):raise SystemExit('FIFA not open')
head=m.read_process_memory(m.base_module,4096);pe=struct.unpack_from('<I',head,60)[0]
rva,size=struct.unpack_from('<II',head,pe+24+112+3*8)
pdata=m.read_process_memory(m.base_module+rva,size)
dis=Cs(CS_ARCH_X86,CS_MODE_64)
for address in (0x331d480,0x331d488,0x331d490,0x331d498):
    pointer=m.read_int64(m.base_module+address)
    try:print('format',hex(address),hex(pointer),m.read_process_memory(pointer,256).split(b'\0')[0],flush=True)
    except Exception:pass
for target in (0x4b4e1e9,0x4b4e810,0x452ed1a,0x4b331a4,0x3d41a18):
    fn=next(((s,e,u) for s,e,u in struct.iter_unpack('<III',pdata) if s<=target<e),None)
    if not fn:continue
    begin,end,unwind=fn;code=m.read_process_memory(m.base_module+begin,end-begin)
    print('function',hex(begin),hex(end),flush=True)
    for i in dis.disasm(code,m.base_module+begin):
        if (target==0x4b4e1e9 and abs(i.address-(m.base_module+target))<190) or target==0x452ed1a or target!=0x4b4e1e9 and abs(i.address-(m.base_module+target))<80:
            extra=''
            if i.mnemonic=='lea' and 'rip' in i.op_str:
                import re
                match=re.search(r'rip ([+-]) (0x[0-9a-f]+)',i.op_str)
                if match:
                    ptr=i.address+i.size+int(match[2],16)*(1 if match[1]=='+' else -1)
                    try:extra=repr(m.read_process_memory(ptr,256).split(b'\0',1)[0])
                    except Exception:pass
            print(hex(i.address),i.mnemonic,i.op_str,extra,flush=True)
m.close()
