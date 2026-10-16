from pathlib import Path
import struct,json,datetime,psutil
p=Path(r'U:\fifa 16\crash.dmp')
data=p.read_bytes()
u=lambda fmt,off:struct.unpack_from('<'+fmt,data,off)
print('dump',json.dumps(dict(bytes=len(data),modified=datetime.datetime.fromtimestamp(p.stat().st_mtime).isoformat(),signature=data[:4].decode(errors='replace'))))
streams={}
if data[:4]==b'MDMP':
    count,rva=u('II',8)
    for i in range(count):
        kind,size,at=u('III',rva+i*12);streams[kind]=(size,at)
    print('streams',streams)
    modules=[]
    if 4 in streams:
        pos=streams[4][1];count=u('I',pos)[0]
        for i in range(count):
            at=pos+4+i*108;base,size,checksum,timestamp,name=u('QIIII',at)
            length=u('I',name)[0];text=data[name+4:name+4+length].decode('utf-16le',errors='replace')
            modules.append((base,size,text))
        print('custom_modules',json.dumps([(hex(b),hex(s),n) for b,s,n in modules if not n.lower().startswith('c:\\windows\\')],ensure_ascii=True))
    def locate(addr):
        return next((f'{Path(n).name}+0x{addr-b:x}' for b,s,n in modules if b<=addr<b+s),'unmapped')
    if 6 in streams:
        at=streams[6][1];thread=u('I',at)[0];code,flags,record,addr,nparams=u('IIQQI',at+8)
        params=u('15Q',at+40);size,context=u('II',at+160)
        print('exception',json.dumps(dict(thread=thread,code=hex(code),address=hex(addr),module=locate(addr),parameters=[hex(x) for x in params[:nparams]])))
        if size>=256:
            regs={n:u('Q',context+o)[0] for n,o in [('rax',120),('rcx',128),('rdx',136),('rbx',144),('rsp',152),('rbp',160),('rsi',168),('rdi',176),('r8',184),('r9',192),('r10',200),('r11',208),('r12',216),('r13',224),('r14',232),('r15',240),('rip',248)]}
            print('registers',{n:hex(v) for n,v in regs.items()})
            ranges=[]
            if 5 in streams:
                pos=streams[5][1]
                for i in range(u('I',pos)[0]):
                    start,length,offset=u('QII',pos+4+i*16);ranges.append((start,length,offset))
            if 9 in streams:
                pos=streams[9][1];count,offset=u('QQ',pos)
                for i in range(count):
                    start,length=u('QQ',pos+16+i*16);ranges.append((start,length,offset));offset+=length
            if 3 in streams:
                pos=streams[3][1]
                for i in range(u('I',pos)[0]):
                    start,length,offset=u('QII',pos+4+i*48+24);ranges.append((start,length,offset))
            def memory(address,length):
                for start,size,offset in ranges:
                    if start<=address<start+size:return data[offset+address-start:offset+address-start+min(length,start+size-address)]
                return b''
            codebytes=memory(addr-24,80);print('code',codebytes.hex())
            try:
                from capstone import Cs,CS_ARCH_X86,CS_MODE_64
                dis=Cs(CS_ARCH_X86,CS_MODE_64)
                print('instructions',[(hex(i.address),i.mnemonic,i.op_str) for i in dis.disasm(memory(addr,56),addr)])
            except ImportError:pass
            import re
            for reg in ('rbx','rsi'):
                block=memory(regs[reg],512)
                print('object',reg,block.hex(),re.findall(rb'[\x20-\x7e]{4,}',block))
                for i in range(0,len(block),8):
                    pointer=struct.unpack_from('<Q',block,i)[0]
                    strings=re.findall(rb'[\x20-\x7e]{4,}',memory(pointer,128))
                    if strings:print('object_pointer',reg,hex(i),hex(pointer),strings)
            stack=memory(regs['rsp'],512)
            print('stack',[(hex(regs['rsp']+i),hex(struct.unpack_from('<Q',stack,i)[0]),locate(struct.unpack_from('<Q',stack,i)[0])) for i in range(0,len(stack),8)])
    import re
    strings=re.findall(rb'[\x20-\x7e]{5,}',data)
    print('captured_strings',[x.decode() for x in strings if any(t in x.lower() for t in (b'loc/',b'por_',b'eng_',b'textcache'))])
for process in psutil.process_iter(['pid','name','exe']):
    if (process.info['name'] or '').lower() in ('fifa16.exe','server16python.exe'):print('running',json.dumps(process.info))
