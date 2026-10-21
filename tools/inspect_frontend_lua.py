"""Read Lua table values in the running FIFA renderer without invoking Lua."""
import json
import struct
import sys
from pathlib import Path
import psutil
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from server16_py.memory_access import Memory

def main():
    p=next(p for p in psutil.process_iter(['name','exe']) if (p.info['name'] or '').lower()=='fifa16.exe')
    m=Memory();m.process_id=p.pid;m.process_handle=m.kernel32.OpenProcess(0x410,False,p.pid);m.base_module=m._get_base_address(p.info['exe'])
    def num(a,f='Q'):return struct.unpack('<'+f,m.read_process_memory(a,struct.calcsize('<'+f)))[0]
    def string(a):
        n=num(a+16)
        return m.read_process_memory(a+24,min(n,512)).decode('utf8',errors='replace')
    def fields(t):
        if num(t+8,'B')!=5:return {}
        power=num(t+11,'B');node=num(t+32)
        if power>14:return {}
        data=m.read_process_memory(node,(1<<power)*40);out={}
        for i in range(1<<power):
            v,tag,k,kt=struct.unpack_from('<Qi4xQi',data,i*40)
            if kt==4:key=string(k)
            elif kt==3:key=str(struct.unpack('<d',struct.pack('<Q',k))[0])
            else:continue
            out[key]=(v,tag)
        for i in range(min(num(t+56,'I'),64)):
            v,tag=struct.unpack('<Qi',m.read_process_memory(num(t+24)+i*16,12))
            if tag:out[str(i+1)]=(v,tag)
        return out
    def value(pair,depth=0):
        bits,tag=pair
        if tag==4:return string(bits)
        if tag==3:return struct.unpack('<d',struct.pack('<Q',bits))[0]
        if tag==1:return bool(bits)
        if tag==5 and depth<3:return {k:value(v,depth+1) for k,v in fields(bits).items() if v[1]}
        return {'tag':tag,'address':hex(bits)}
    try:
        vm=num(m.base_module+0x3613fd0);g=fields(num(vm+0x78))
        db=fields(g['db'][0]);render=fields(g['gRenderObj'][0])
        report={'pid':p.pid,'globals':{k:value(v,2) for k,v in g.items() if k.startswith('Server16Frontend')},
                'stadium':value(db['stadium']), 'crowd':value(db['crowd']), 'render':{k:value(v,2) for k,v in render.items() if 'stad' in k.lower() or 'crowd' in k.lower()}}
        crowd_object=num(m.base_module+0x3504748);crowd_state=num(crowd_object+0x10);crowd_impl=num(num(crowd_state+0x90))
        report['native_crowd']={'object':hex(crowd_object),'state':hex(crowd_state),'implementation':hex(crowd_impl),
                                'stadium':num(crowd_impl+0xf14,'I'),'light':num(crowd_impl+0xf18,'I'),
                                'placement_handle':hex(num(crowd_impl+0x1250))}
        obj=num(m.base_module+0x3504648);state=num(obj+0x20)
        buckets=[]
        for i in range(16):
            begin,end,capacity=struct.unpack('<3Q',m.read_process_memory(state+0x2060+i*0x30,24))
            count=(end-begin)//0x50
            if end<begin or capacity<end or (end-begin)%0x50 or count>512:continue
            rows=[]
            visibility=num(state+0x1ed0)
            for j in range(count):
                raw=m.read_process_memory(begin+j*0x50,0x50)
                vis=num(visibility+j*4,'I') if i==1 and visibility else None
                ptr=num(begin+j*0x50+8)
                descriptor=m.read_process_memory(ptr,40).hex() if ptr else ''
                rows.append({'raw':raw.hex(),'visibility':vis,'descriptor':descriptor})
            buckets.append({'bucket':i,'count':count,'rows':rows})
        resource=num(state+0xcc8)
        report['native_stadium']={'object':hex(obj),'state':hex(state),'flags':m.read_process_memory(state,16).hex(),
                                  'group_enabled':m.read_process_memory(state+0x1ef8,16).hex(),
                                  'cull_flags':m.read_process_memory(state+0x1fc0,16).hex(),
                                  'resource':hex(resource),'resource_data':m.read_process_memory(resource,256).hex() if resource else None,'buckets':buckets}
        path=ROOT/'artifacts/frontend_stadium_research/lua-live.json';path.write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report,indent=2))
    finally:m.close()

if __name__=='__main__':main()
