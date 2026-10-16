"""Remove measured boundary silence with generous word-preserving margins."""
from pathlib import Path
import json,hashlib,subprocess
from core import connect,GAME,WORK,FFMPEG,import_sources
from projects import folder

def clean():
    report=json.loads((GAME/'Narrations/Luiz Roberto/audio_quality_report.json').read_text(encoding='utf8'))
    dest=folder('Luiz Roberto')/'source/clean_boundaries';dest.mkdir(parents=True,exist_ok=True)
    pending=[]
    for row in report['audio']:
        stats=row['source'];start=max(0,stats['leading']-.18) if stats['leading']>.35 else 0
        end=stats['duration']-max(0,stats['trailing']-.25) if stats['trailing']>.7 else stats['duration']
        if not start and end==stats['duration']:continue
        src=Path(row['path']);target=dest/(src.stem+'_clean.wav')
        subprocess.run([FFMPEG,'-v','error','-y','-i',str(src),'-ss',str(start),'-t',str(end-start),'-ac','1','-ar','32000','-c:a','pcm_s16le',str(target)],check=True,capture_output=True,creationflags=0x08000000)
        pending.append(dict(original=str(src),path=str(target),start=start,end=end,transcript=row['transcript']))
    import_sources('Luiz Roberto',dest);db=connect();changed=0
    for row in pending:
        original=db.execute('SELECT * FROM sources WHERE narrator=? AND path=?',('Luiz Roberto',row['original'])).fetchone()
        replacement=db.execute('SELECT key FROM sources WHERE narrator=? AND path=?',('Luiz Roberto',row['path'])).fetchone()[0]
        db.execute('UPDATE sources SET event=?,variant=?,transcript=?,confidence=?,duration=?,topic=? WHERE key=?',(original['event'],original['variant'],original['transcript'],original['confidence'],row['end']-row['start'],original['topic'],replacement))
        changed+=db.execute("UPDATE mappings SET source=?,method='boundary_cleanup' WHERE profile='Luiz Roberto' AND source=?",(replacement,original['key'])).rowcount
    db.commit();db.close();(dest/'origins.json').write_text(json.dumps(pending,ensure_ascii=False,indent=2),encoding='utf8');print('Boundary cleanup',len(pending),'sources;',changed,'occurrences',flush=True)

if __name__=='__main__':clean()
