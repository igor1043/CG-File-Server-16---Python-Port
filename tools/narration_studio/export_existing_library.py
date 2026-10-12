"""Expose existing recordings and transcripts without changing live profiles."""
from pathlib import Path
import json,os,shutil
from core import connect
from pes_extract_library import DEFAULT_ROOT

def run():
    db=connect();rows=db.execute("SELECT key,narrator,path,transcript,duration FROM sources WHERE narrator IN ('Vilani','Luiz Roberto')").fetchall();db.close()
    grouped={};folders={};available={}
    for row in rows:
        source=Path(row['path'])
        if source.parent not in available:
            try:
                with os.scandir(source.parent) as entries:available[source.parent]={entry.name for entry in entries}
            except OSError:available[source.parent]=set()
        if source.name not in available[source.parent]:continue
        dest=DEFAULT_ROOT/row['narrator']/'original'/'biblioteca_anterior'/source.parent.name/source.name
        if dest.parent not in folders:
            dest.parent.mkdir(parents=True,exist_ok=True)
            with os.scandir(dest.parent) as entries:folders[dest.parent]={entry.name for entry in entries}
        if dest.name not in folders[dest.parent]:
            try:os.link(source,dest)
            except OSError:shutil.copy2(source,dest)
        sidecar=dest.with_suffix(dest.suffix+'.txt')
        if row['transcript'] and sidecar.name not in folders[dest.parent]:sidecar.write_text(row['transcript'],encoding='utf8')
        grouped.setdefault(row['narrator'],[]).append(dict(key=row['key'],audio=str(dest),origin=str(source),transcript=row['transcript'],duration=row['duration']))
        if sum(len(items) for items in grouped.values())%1000==0:print('Biblioteca anterior:',sum(len(items) for items in grouped.values()),flush=True)
    for name,items in grouped.items():
        (DEFAULT_ROOT/name/'biblioteca_anterior.json').write_text(json.dumps(items,ensure_ascii=False,indent=2),encoding='utf8')
        print(name,len(items),flush=True)
if __name__=='__main__':run()
