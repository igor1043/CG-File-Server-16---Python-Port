from pathlib import Path
import struct, sys, json, subprocess, re
from research_narration import big_entries, OUT, ROOT
for entry in big_entries(ROOT/'por_br.big'):
    if entry['name'].endswith('.sbr'):
        p=OUT / Path(entry['name']).name
        with (ROOT/'por_br.big').open('rb') as f:
            f.seek(entry['offset']); p.write_bytes(f.read(entry['size']))
for p in OUT.glob('*.sbr'):
    b=p.read_bytes(); nd=struct.unpack_from('<H',b,10)[0]; table=struct.unpack_from('<I',b,24)[0]
    print(p.name,len(b),b[:48].hex(' '),'DSETS',nd,'TABLE',table)
    for i in range(min(3,nd)):
        d=struct.unpack_from('<I',b,table+8*i)[0]
        nv=struct.unpack_from('<I',b,d+0x38)[0]
        nf=struct.unpack_from('<H',b,d+0x3c)[0]
        print(' DSET',hex(d),'ID',hex(struct.unpack_from('<I',b,d+8)[0]),'VALUES',nv,'FIELDS',nf)
        for j in range(nf):
            field=b[d+0x48+24*j:d+0x48+24*(j+1)]
            print('  FIELD',field.hex(' '))
    print('STRINGS', [s[:80].decode('ascii') for s in re.findall(rb'[A-Za-z_]{10,}',b)][:8])
    for i in range(nd):
        d=struct.unpack_from('<I',b,table+8*i)[0]
        nv=struct.unpack_from('<I',b,d+56)[0]
        nf=struct.unpack_from('<H',b,d+60)[0]
        for j in range(nf):
            pos=d+72+24*j
            if b[pos+5]==3:
                ptr,idx=struct.unpack_from('<II',b,pos+16)
                print('TYPE3',i,nv,b[pos:pos+24].hex(),'VALUES',b[ptr:ptr+32].hex(),'INDEX',b[idx:idx+32].hex())
import zlib
for p in OUT.glob('meta_*'):
    b=p.read_bytes()
    if b[:8]!=b'chunkzip': continue
    blocks=struct.unpack_from('>I',b,20)[0]
    pos=40; parts=[]
    for _ in range(blocks):
        pos = ((pos+7)//8)*8
        if pos%16!=8: pos+=8
        length,flag=struct.unpack_from('>II',b,pos)
        chunk=b[pos+8:pos+8+length]
        try: decoded=zlib.decompress(chunk,-15) if flag==1 else chunk
        except zlib.error as e: print('ZIPERROR',p.name,pos,length,flag,e); break
        parts.append(decoded); pos+=8+length
    if parts:
        target=p.with_name('decoded_'+p.name)
        target.write_bytes(b''.join(parts))
        print('DECOMPRESSED',p.name,blocks,len(b''.join(parts)),repr(b''.join(parts)[:100]))
