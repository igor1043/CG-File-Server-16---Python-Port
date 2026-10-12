from pathlib import Path
import struct, zlib, xml.etree.ElementTree as ET, collections
from research_narration import OUT
xml=ET.fromstring((OUT/'decoded_meta_por_br.xml').read_bytes())
keys={int(x.attrib['SampleGroupKey'],16):x.attrib['Name'] for x in xml.iter('SampleGroup')}
for p in OUT.glob('*.sbr'):
    b=p.read_bytes(); table=struct.unpack_from('<I',b,24)[0]
    matches=[0]*10; samples=[]
    for i in range(struct.unpack_from('<H',b,10)[0]):
        d=struct.unpack_from('<I',b,table+i*8)[0]
        for k in range(10):
            value=struct.unpack_from('<I',b,d+8+4*k)[0]
            if value in keys:
                matches[k]+=1
                if len(samples)<3: samples.append((i,k,keys[value]))
    print(p.name,matches,samples)
print('GROUPS',len(keys))
print('RONALDINHO',[(k,v) for k,v in keys.items() if 'RONALD' in v])
