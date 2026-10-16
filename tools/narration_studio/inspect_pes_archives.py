from pathlib import Path
import json,struct,subprocess,collections

root=Path(__file__).parent
data=json.loads((root/'pes_inventory.json').read_text(encoding='utf8'))
result=[]
for entry in data['narrators']:
    folder=Path(r'J:\mods\pes\audio pes\content\Multinarrador')/entry['name']
    banks=[]
    for awb in sorted(folder.rglob('*.awb')):
        with awb.open('rb') as file:
            head=file.read(16)
            if head[:4]!=b'AFS2':
                banks.append(dict(file=str(awb),header=head.hex()));continue
            version,offset_size,id_size,unknown=head[4:8]
            count,alignment,key=struct.unpack_from('<IHH',head,8)
            ids=file.read(count*id_size)
            offsets=file.read((count+1)*offset_size)
            samples=[]
            for index in (0,count//2,count-1):
                begin=int.from_bytes(offsets[index*offset_size:(index+1)*offset_size],'little')
                begin=(begin+alignment-1)//alignment*alignment
                end=int.from_bytes(offsets[(index+1)*offset_size:(index+2)*offset_size],'little')
                file.seek(begin);sample=file.read(min(end-begin,100))
                samples.append(dict(index=index,id=int.from_bytes(ids[index*id_size:(index+1)*id_size],'little'),size=end-begin,header=sample.hex()))
            banks.append(dict(file=str(awb),count=count,bytes=awb.stat().st_size,version=version,offset_size=offset_size,id_size=id_size,alignment=alignment,key=key,samples=samples))
    result.append(dict(name=entry['name'],banks=banks))
(root/'pes_archives.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
for item in result:
    print(json.dumps(dict(name=item['name'],banks=[dict(name=Path(b['file']).name,count=b.get('count'),bytes=b.get('bytes'),key=b.get('key')) for b in item['banks']]),ensure_ascii=True),flush=True)
print(json.dumps(result[0],ensure_ascii=True),flush=True)
