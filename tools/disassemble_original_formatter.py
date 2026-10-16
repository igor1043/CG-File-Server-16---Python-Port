from pathlib import Path
import struct
from capstone import Cs,CS_ARCH_X86,CS_MODE_64
for path in (Path(r'U:\fifa 16\fifa16.bin'),Path(r'U:\fifa 16\fifa16.exe')):
    data=path.read_bytes();pe=struct.unpack_from('<I',data,60)[0]
    count,opt=struct.unpack_from('<H',data,pe+6)[0],struct.unpack_from('<H',data,pe+20)[0]
    sections=[struct.unpack_from('<8sIIII',data,pe+24+opt+i*40) for i in range(count)]
    for rva in (0x3c987e0,0x3c9a720,0x3c9e270,0x3a34200):
        for name,size,start,rawsize,offset in sections:
            if start<=rva<start+size:
                code=data[offset+rva-start:offset+rva-start+512]
                print(path.name,hex(rva),code[:16].hex())
                if rva in (0x3c987e0,0x3c9a720,0x3a34200):
                    dis=Cs(CS_ARCH_X86,CS_MODE_64)
                    for i in dis.disasm(code,0x140000000+rva):
                        print(hex(i.address),i.mnemonic,i.op_str)
                        if i.mnemonic=='ret':break
