"""Bounded read-only snapshot of the active native manager-job service."""
import ctypes,json,struct,sys
from pathlib import Path
import psutil
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from server16_py.memory_access import Memory,MODULEENTRY32W,TH32CS_SNAPMODULE,TH32CS_SNAPMODULE32,INVALID_HANDLE_VALUE
from server16_py.career_context import _export,competition_session
from server16_py.career_save_worker import read_job_offer,fingerprint

def main():
 p=next(p for p in psutil.process_iter(['name','exe']) if (p.info['name'] or '').lower()=='fifa16.exe')
 m=Memory();m.process_id=p.pid;m.process_handle=m.kernel32.OpenProcess(0x410,False,p.pid);m.base_module=m._get_base_address(p.info['exe'])
 snapshot=m.kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE|TH32CS_SNAPMODULE32,p.pid)
 try:
  entry=MODULEENTRY32W();entry.dwSize=ctypes.sizeof(entry);ok=m.kernel32.Module32FirstW(snapshot,ctypes.byref(entry));modules=[]
  while ok:
   if entry.szModule.lower()=='dinput8.dll':modules.append((ctypes.addressof(entry.modBaseAddr.contents),entry.modBaseSize))
   ok=m.kernel32.Module32NextW(snapshot,ctypes.byref(entry))
 finally:m.kernel32.CloseHandle(snapshot)
 report={'pid':p.pid,'profile':competition_session(m,details=True),'ram_write_access':False}
 offsets=json.loads((ROOT/'server16_py/offsets.json').read_text())
 report['page']=m.get_string(offsets['ORIPGBASE'],offsets['PG1'],64)
 for base,size in modules:
  exported=_export(m,base,size,b'Fifa16CareerGetState')
  if exported is None:continue
  code=m.read_process_memory(exported,96)
  marker=bytes.fromhex('488d542450488d4c2440e8');pos=code.find(marker)
  if pos<0:report['accessor_code']=code.hex();continue
  call=exported+pos+10;live=call+5+struct.unpack_from('<i',code,pos+11)[0]
  body=m.read_process_memory(live,64);at=body.find(bytes.fromhex('488b3d'))
  global_addr=live+at+7+struct.unpack_from('<i',body,at+3)[0]
  owner=m.read_int64(global_addr);registry=m.read_int64(owner+8)
  job=m.read_int64(m.read_int64(registry+54*32+24))
  offer=list(struct.unpack('<11i',m.read_process_memory(job+0x158,44)))
  start,end,cap=struct.unpack('<3Q',m.read_process_memory(job+0xd8,24))
  report.update(native_module=hex(base),owner=hex(owner),registry=hex(registry),job_manager=hex(job),
   job_vtable=hex(m.read_int64(job)-m.base_module),offer_vtable=hex(m.read_int64(job+0x150)-m.base_module),
   offer=offer,vector_range=[hex(v) for v in (start,end,cap)],
   functions={hex(a):m.read_process_memory(m.base_module+a,8).hex() for a in (0x5aa4120,0x5b57860,0x5bcfaa0)},
   manager_state={hex(a):m.read_uint32(job+a) for a in (0x11c,0x128,0x140,0x144,0x14)})
  if 0<=end-start<=512*32 and (end-start)%32==0:
   report['vacancies']=[list(row) for row in struct.iter_unpack('<8i',m.read_process_memory(start,end-start))] if end>start else []
 m.close()
 bridge=Path('U:/fifa 16/ModCarrerMode/runtime/career_save_source.tsv')
 record=dict(line.split('=',1) for line in bridge.read_text(encoding='utf8').splitlines() if '=' in line)
 data=Path(record['path']).read_bytes();report.update(save_path=record['path'],save_sha256=fingerprint(data),saved_offer=read_job_offer(data))
 out=ROOT/'artifacts/career_jobs_live_review';out.mkdir(exist_ok=True)
 (out/'live.json').write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report,indent=2))

if __name__=='__main__':main()

