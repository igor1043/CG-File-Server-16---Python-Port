"""Read the FE bridge and scene state without calling or changing game code."""
import ctypes
import json
import struct
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from server16_py.memory_access import Memory, MODULEENTRY32W, INVALID_HANDLE_VALUE
from server16_py.offsets import Offsets
from server16_py.career_context import _export, competition_session


def main():
    import psutil
    process=next((p for p in psutil.process_iter(['name','exe']) if (p.info['name'] or '').lower()=='fifa16.exe'),None)
    if process is None:
        print(json.dumps({'running':False,'ram_write_access':False}));return
    memory=Memory();memory.process_id=process.pid
    memory.process_handle=memory.kernel32.OpenProcess(0x410,False,process.pid)
    memory.base_module=memory._get_base_address(process.info['exe'])
    base=memory.base_module;offsets=Offsets()
    report={'running':True,'pid':process.pid,'ram_write_access':False,'module_loaded':False}
    try:
        report['page']=memory.get_string(offsets.ORIPGBASE,offsets.PG1,96)
        stadium=memory.read_int64(base+0x3504648)
        state=memory.read_int64(stadium+0x20)
        table=state+0xa90
        report['scene']={'stadium_id':memory.read_uint32(table+0x18),'light':memory.read_uint32(table+0x1c),
                         'native_home_team':memory.read_uint32(table+0x44),
                         'loaded':bool(memory.read_process_memory(state+1,1)[0])}
        report['career']=competition_session(memory,details=True)
        service=memory.read_int64(base+0x34ea0e8)
        commands=memory.read_int64(service+0x68)
        handlers=memory.read_int64(commands)
        for i in range(3):
            native=memory.read_int64(handlers+i*8)
            if not native:continue
            vtable=memory.read_int64(native)
            if memory.read_int64(vtable+8)!=base+0x3d8e370:continue
            native_state=memory.read_uint32(native+0x30)
            report['native_reload']={'state':native_state,'previous':memory.read_uint32(native+0x34),
                                     'waiting_background':native_state==14,
                                     'pending_stadium':memory.read_uint32(native+0xb0)}
            break
        snapshot=memory.kernel32.CreateToolhelp32Snapshot(24,process.pid)
        if snapshot and snapshot!=INVALID_HANDLE_VALUE:
            try:
                entry=MODULEENTRY32W();entry.dwSize=ctypes.sizeof(entry)
                ok=memory.kernel32.Module32FirstW(snapshot,ctypes.byref(entry))
                while ok:
                    if entry.szModule.lower().startswith('frontend_stadium_native_'):
                        module=ctypes.addressof(entry.modBaseAddr.contents)
                        report.update(module_loaded=True,module_path=entry.szExePath)
                        status=_export(memory,module,entry.modBaseSize,b'FrontendStadiumStatus')
                        if status:
                            data=memory.read_process_memory(status,104)
                            names=('version','size','ready','team','slot','career','requests','applied','error','photo_hidden')
                            report['bridge']=dict(zip(names,struct.unpack_from('<10I',data)))
                            report['bridge']['previous_image']=data[40:104].split(b'\0',1)[0].decode('ascii',errors='replace')
                        for label,source in [('scene_call',0x43630eb),('photo_call',0x408d206),
                                             ('boot_monitor',0x3a1a168),('scene_monitor',0x3a19f7f)]:
                            code=memory.read_process_memory(base+source,5)
                            destination=base+source+5+struct.unpack_from('<i',code,1)[0]
                            relay=memory.read_process_memory(destination,14)
                            target=struct.unpack_from('<Q',relay,6)[0] if relay[:6]==b'\xff\x25\0\0\0\0' else 0
                            report[label]={'relayed':bool(target),'target_inside_module':module<=target<module+entry.modBaseSize}
                    ok=memory.kernel32.Module32NextW(snapshot,ctypes.byref(entry))
            finally:memory.kernel32.CloseHandle(snapshot)
    except (RuntimeError,OSError,ValueError) as error:
        report['read_error']=str(error)
    finally:memory.close()
    print(json.dumps(report,indent=2))
    out=ROOT/'artifacts/frontend_stadium_research/live.json'
    out.write_text(json.dumps(report,indent=2),encoding='utf8')

if __name__=='__main__':main()
