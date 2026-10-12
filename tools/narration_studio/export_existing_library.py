"""Expose existing recordings and transcripts without changing live profiles."""
from pathlib import Path
import json,os,shutil
from core import connect
from pes_extract_library import DEFAULT_ROOT

def run():
    db=connect();rows=db.execute("SELECT key,narrator,path,transcript,duration FROM sources WHERE narrator IN ('Vilani','Luiz Roberto')").fetchall();db.close()
    grouped={}
    for row in rows:
        source=Path(row['path'])
        if not source.exists():continue
        dest=DEFAULT_ROOT/row['narrator']/'original'/'biblioteca_anterior'/source.parent.name/source.name
        dest.parent.mkdir(parents=True,exist_ok=True)
        if not dest.exists():
            try:os.link(source,dest)
            except OSError:shutil.copy2(source,dest)
        if row['transcript']:dest.with_suffix(dest.suffix+'.txt').write_text(row['transcript'],encoding='utf8')
        grouped.setdefault(row['narrator'],[]).append(dict(key=row['key'],audio=str(dest),origin=str(source),transcript=row['transcript'],duration=row['duration']))
    for name,items in grouped.items():
        (DEFAULT_ROOT/name/'biblioteca_anterior.json').write_text(json.dumps(items,ensure_ascii=False,indent=2),encoding='utf8')
        print(name,len(items),flush=True)
if __name__=='__main__':run()
