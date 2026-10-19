import sys,json,struct
from pathlib import Path
sys.path.insert(0,str(Path.cwd()));sys.path.insert(0,str(Path.cwd()/'runtime/dev_deps'))
import psutil
from capstone import *
from server16_py.memory_access import Memory
p=next(p for p in psutil.process_iter(['name','exe']) if (p.info['name'] or '').lower()=='fifa16.exe')
m=Memory();m.process_id=p.pid;m.process_handle=m.kernel32.OpenProcess(0x410,False,p.pid);m.base_module=m._get_base_address(p.info['exe'])
d=Cs(CS_ARCH_X86,CS_MODE_64);d.skipdata=True
out=Path('artifacts/career_jobs_disassembly')
for arg in sys.argv[1:]:
 a,n=(int(x,16) for x in arg.split(':'))
 code=m.read_process_memory(m.base_module+a,n)
 (out/(f'{a:08x}_range.asm')).write_text('\n'.join(f'{i.address:08x} {i.mnemonic:8} {i.op_str}' for i in d.disasm(code,a)),encoding='utf8')
m.close()
