"""Locate the menu photograph in installed BIG/SWF assets, read-only."""
import json
import re
import struct
import sys
import zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from server16_py.narration_bank import BigArchive

def unpack(data):
    if data[:8]==b'chunkzip':
        version,full,chunk,count=struct.unpack_from('>IIII',data,8)
        if version!=2 or full>32*1024*1024 or count>1024:return data
        parts=[];pos=40
        for _ in range(count):
            pos=(pos+7)//8*8
            if pos%16!=8:pos+=8
            size,flag=struct.unpack_from('>II',data,pos)
            payload=data[pos+8:pos+8+size]
            parts.append(payload if flag==4 else zlib.decompress(payload,-15))
            pos+=8+size
        data=b''.join(parts)
        if len(data)!=full:raise ValueError('truncated chunkzip')
    if data[:3] in (b'CWS',b'CFX'):
        data=b'F'+data[1:8]+zlib.decompress(data[8:])
    return data

def main():
    game=Path(sys.argv[1]) if len(sys.argv)>1 else Path('U:/fifa 16')
    out=ROOT/'artifacts/frontend_stadium_research/ui';out.mkdir(parents=True,exist_ok=True)
    paths=list((game/'data/ui/game').rglob('*.big'))
    paths.extend(game/name for name in ('data_front_end.big','data_front_end_extra.big','data_startup.big','data_patch.big'))
    hits=[];count=0
    for path in paths:
        try:archive=BigArchive(path)
        except (ValueError,OSError):continue
        for entry in archive.entries:
            if entry.name.lower().endswith(('.dds','.rx3','.png','.jpg','.wav')):continue
            if not 0<entry.size<32*1024*1024:continue
            try:data=unpack(archive.read(entry))
            except (ValueError,zlib.error):continue
            count+=1
            term=re.compile(rb'backgroundstadium|st_bootflow|notfound.dds',re.I)
            matches=list(term.finditer(data))
            if matches:
                filename=f'{len(hits):03d}_'+Path(entry.name).name
                (out/filename).write_bytes(data)
                record={'archive':str(path),'entry':entry.name,'file':filename,'contexts':[
                    repr(data[max(0,m.start()-80):m.end()+100]) for m in matches[:12]]}
                hits.append(record);print(json.dumps(record),flush=True)
    (out/'findings.json').write_text(json.dumps({'files_scanned':count,'hits':hits},indent=2),encoding='utf8')
    print('scanned',count,'hits',len(hits))
if __name__=='__main__':main()
