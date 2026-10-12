"""Add extracted PES references to the editable catalogue, retaining provenance."""
from pathlib import Path
import json,sqlite3
from core import connect
from topics import topic
from pes_extract_library import DEFAULT_ROOT,WORK

def run(root=DEFAULT_ROOT):
    library=sqlite3.connect(root/'library.sqlite');library.row_factory=sqlite3.Row
    assets={row['sha']:dict(row) for row in library.execute("SELECT * FROM assets WHERE status='decoded'")};library.close()
    db=connect();summary=[]
    for index in (WORK.parent.parent.parent/'narrações fifa').glob('*/indexes/pes_references.json'):
        refs=json.loads(index.read_text(encoding='utf8'));seen=set();count=0
        for ref in refs:
            sha=ref['sha256']
            if sha in seen or sha not in assets:continue
            seen.add(sha);asset=assets[sha]
            if asset['duration']<=.25 or not asset['transcript'] or asset['transcript']=='[sem fala detectada]':continue
            name=ref['narrator'];key=name+':pes:'+sha
            path=root/name/'original'/ref['bank']/(str(ref['id'])+'_'+str(ref['index'])+'.flac')
            if not path.is_file():continue
            text=asset['transcript'];event=''
            db.execute('''INSERT INTO sources(key,narrator,path,event,variant,transcript,duration,error,topic)
                VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(key) DO UPDATE SET transcript=excluded.transcript,duration=excluded.duration,topic=excluded.topic''',
                (key,name,str(path),event,-1,text,asset['duration'],'',topic(event,str(path),text)))
            count+=1
        db.commit();summary.append(dict(narrator=refs[0]['narrator'] if refs else index.parent.parent.name,sources=count))
    db.close();print(json.dumps(summary,ensure_ascii=True),flush=True)
    return summary
if __name__=='__main__':run()
