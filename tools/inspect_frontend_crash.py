"""Read a saved minidump; does not access or change a running process."""
import json
import struct
import sys
from pathlib import Path

def inspect(path):
    data=Path(path).read_bytes()
    def unpack(fmt,offset):return struct.unpack_from('<'+fmt,data,offset)
    count,directory=unpack('II',8)
    streams={kind:(size,rva) for kind,size,rva in (unpack('III',directory+i*12) for i in range(count))}
    modules=[]
    at=streams[4][1]
    for i in range(unpack('I',at)[0]):
        base,size,checksum,stamp,name=unpack('QIIII',at+4+i*108)
        length=unpack('I',name)[0]
        text=data[name+4:name+4+length].decode('utf16')
        modules.append((base,size,Path(text).name))
    def locate(address):
        return next((f'{name}+0x{address-base:x}' for base,size,name in modules if base<=address<base+size),hex(address))
    report={'path':str(path)}
    if 6 in streams:
        at=streams[6][1]
        tid=unpack('I',at)[0]
        code,flags,record,address=unpack('IIQQ',at+8)
        parameters=unpack('I',at+32)[0]
        size,context=unpack('II',at+160)
        report['exception']={'thread':tid,'code':hex(code),'address':locate(address),
                             'parameters':[hex(v) for v in unpack('Q'*min(parameters,15),at+40)]}
        if size>=256:
            report['exception']['rip']=locate(unpack('Q',context+248)[0])
            report['exception']['registers']={label:hex(unpack('Q',context+offset)[0]) for label,offset in
                [('rax',120),('rcx',128),('rdx',136),('rbx',144),('rsp',152),('rbp',160),('rsi',168),('rdi',176),('r8',184),('r9',192)]}
    at=streams[3][1];threads=[]
    for i in range(unpack('I',at)[0]):
        row=at+4+i*48
        tid=unpack('I',row)[0]
        stack_address,stack_size,stack_rva=unpack('QII',row+24)
        context_size,context=unpack('II',row+40)
        if context_size<256:continue
        rip=unpack('Q',context+248)[0];rsp=unpack('Q',context+152)[0]
        if tid==report.get('exception',{}).get('thread'):
            rsp=int(report['exception'].get('registers',{}).get('rsp',hex(rsp)),16)
        offset=max(0,rsp-stack_address)
        stack=data[stack_rva+offset:stack_rva+min(stack_size,offset+4096)]
        values=[]
        for j in range(0,len(stack)-7,8):
            value=struct.unpack_from('<Q',stack,j)[0]
            where=locate(value)
            if '+' in where:values.append({'offset':hex(j),'module':where})
        if tid==report.get('exception',{}).get('thread'):
            report['crashed_thread']={'tid':tid,'rip':locate(rip),'stack':values[:48]}
    return report

if __name__=='__main__':print(json.dumps(inspect(sys.argv[1]),indent=2))
