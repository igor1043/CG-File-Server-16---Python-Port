from pathlib import Path
import subprocess,sys,time,json,shutil,datetime,psutil
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server16_py.memory_access import Memory
from server16_py.offsets import Offsets
game=Path(r'U:\fifa 16');out=game/'runtime/crash_investigation'/datetime.datetime.now().strftime('%Y%m%d_%H%M%S');out.mkdir(parents=True)
for path in (game/'crash.dmp',game/'runtime/server16.log',game/'dinput8_L9.log'):
    if path.exists():shutil.copy2(path,out/path.name)
process=next((p for p in psutil.process_iter(['name']) if (p.info['name'] or '').lower()=='fifa16.exe'),None)
launched=None
if process is None:
    launched=subprocess.Popen([str(game/'fifa16.exe')],cwd=game)
    process=psutil.Process(launched.pid)
print(json.dumps(dict(pid=process.pid,evidence=str(out),launched=launched is not None)),flush=True)
m=Memory();offset=Offsets();deadline=time.monotonic()+240;last='';captured=False
while time.monotonic()<deadline:
    if not process.is_running():
        print(json.dumps(dict(state='exited',exitcode=launched.poll() if launched else None)),flush=True);break
    try:
        if m.attack('fifa16'):
            if not captured and m.read_process_memory(m.base_module+0x4b4e1c0,16)[:1]!=b'\0':
                code=m.read_process_memory(m.base_module+0x4b4dd00,0x1000)
                (out/'fault_function.bin').write_bytes(code);captured=True
            page=m.get_string(offset.ORIPGBASE,offset.PG1,64)
            if page!=last:print(json.dumps(dict(state='page',page=page)),flush=True);last=page
            if page and time.monotonic()>deadline-150:
                print(json.dumps(dict(state='startup_survived',page=page)),flush=True);break
    except Exception:pass
    time.sleep(.5)
else:print(json.dumps(dict(state='alive',page=last)),flush=True)
m.close()
for path in (game/'crash.dmp',game/'runtime/server16.log',game/'dinput8_L9.log'):
    if path.exists():shutil.copy2(path,out/('after_'+path.name))
