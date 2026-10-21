"""Capture a small thread/stack diagnostic for an already hung FIFA process."""
import ctypes
import json
import struct
from ctypes import wintypes
from pathlib import Path
import psutil

OUT=Path(r'C:\Users\igorv\AppData\Local\Temp\server16_frontend_hang_20261020')


def main():
    process=next(p for p in psutil.process_iter(['name']) if (p.info['name'] or '').lower()=='fifa16.exe')
    OUT.mkdir(parents=True,exist_ok=True)
    path=OUT/f'fifa_{process.pid}.dmp'
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    debug=ctypes.WinDLL('dbghelp',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    debug.MiniDumpWriteDump.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.HANDLE,wintypes.DWORD,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p]
    debug.MiniDumpWriteDump.restype=wintypes.BOOL
    handle=kernel.OpenProcess(0x410,False,process.pid)
    if not handle:raise ctypes.WinError(ctypes.get_last_error())
    import msvcrt
    try:
        with path.open('wb') as output:
            ok=debug.MiniDumpWriteDump(handle,process.pid,msvcrt.get_osfhandle(output.fileno()),0x1020,None,None,None)
        if not ok:raise ctypes.WinError(ctypes.get_last_error())
    finally:kernel.CloseHandle(handle)
    data=path.read_bytes()
    unpack=lambda fmt,offset:struct.unpack_from('<'+fmt,data,offset)
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
        return next((f'{name}+0x{address-base:x}' for base,size,name in modules if base<=address<base+size),None)
    at=streams[3][1];threads=[]
    times={item.id:item.user_time+item.system_time for item in process.threads()}
    for i in range(unpack('I',at)[0]):
        row=at+4+i*48
        tid=unpack('I',row)[0]
        stack_address,stack_size,stack_rva=unpack('QII',row+24)
        context_size,context=unpack('II',row+40)
        if context_size<256:continue
        rip=unpack('Q',context+248)[0];rsp=unpack('Q',context+152)[0]
        values=[]
        offset=max(0,rsp-stack_address)
        stack=data[stack_rva+offset:stack_rva+min(stack_size,offset+4096)]
        for j in range(0,len(stack)-7,8):
            value=struct.unpack_from('<Q',stack,j)[0]
            location=locate(value)
            if location:values.append({'offset':hex(j),'address':hex(value),'module':location})
        threads.append({'tid':tid,'cpu_seconds':times.get(tid),'rip':hex(rip),'location':locate(rip),'stack':values[:36]})
    report={'pid':process.pid,'dump':str(path),'dump_bytes':len(data),'threads':threads}
    (OUT/'threads.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    for thread in threads:
        if any('fifa16.exe' in item['module'] or 'frontend_stadium' in item['module'] for item in thread['stack'][:18]):
            print(json.dumps(thread))
    print('Captured',len(threads),'threads at',str(path))

if __name__=='__main__':main()
