"""One-shot completion step for the already running original ASR batch."""
import argparse,json,time
from pathlib import Path
import psutil
from core import connect,WORK

def finish(pid):
    try:
        process=psutil.Process(pid)
        if 'transcribe_batch.py' in ' '.join(process.cmdline()):
            while process.is_running():
                try:process.wait(timeout=5);break
                except psutil.TimeoutExpired:pass
    except psutil.NoSuchProcess:pass
    db=connect();pending=db.execute("SELECT count(DISTINCT wav) FROM clips WHERE status='decoded' AND transcript=''").fetchone()[0];db.close()
    if pending:
        from transcribe_batch import run
        # Resume a failed/interrupted inference batch, preserving completed rows.
        run('original',batch_size=4)
    from export_catalog_indexes import export
    from projects import save
    export();save('Tiago Leifert')
    db=connect();pending=db.execute("SELECT count(*) FROM clips WHERE transcript=''").fetchone()[0];db.close()
    result=dict(state='complete' if not pending else 'pending',pending_occurrences=pending)
    (WORK/'original_completion.json').write_text(json.dumps(result,indent=2),encoding='utf8');print(result,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--pid',type=int,required=True);a=p.parse_args();finish(a.pid)
