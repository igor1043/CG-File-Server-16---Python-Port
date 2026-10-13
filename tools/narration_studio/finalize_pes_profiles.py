"""Continue ingestion and reviewed-content proposals after ASR completes.

Runs as an explicit local batch, not a scheduled task. Manual associations are
preserved. Each narrator has independent progress and a restartable build.
"""
from pathlib import Path
import os,json,sqlite3,time,subprocess,sys
import psutil
ROOT=Path(__file__).parent
RAW=Path(r'J:\mods\fifa 16\audios narradores')
GAME=Path(r'U:\fifa 16')

def run():
    while True:
        try:
            state=json.loads((RAW/'progress.json').read_text(encoding='utf8'))
            db=sqlite3.connect(RAW/'library.sqlite',timeout=60)
            pending=db.execute("SELECT count(*) FROM assets WHERE status='decoded' AND transcript IS NULL").fetchone()[0];db.close()
            active_asr=False
            for process in psutil.process_iter(['cmdline']):
                args=process.info['cmdline'] or []
                if any(Path(arg).name=='pes_extract_library.py' for arg in args) and 'transcribe' in args:active_asr=True;break
            if state.get('state')=='complete' and not pending and not active_asr:break
        except (OSError,ValueError,sqlite3.Error):pass
        time.sleep(20)
    while not (GAME/'Narrations/.studio/catalog_ready.json').exists():
        try:
            db=sqlite3.connect(GAME/'Narrations/.studio/catalog.sqlite',timeout=60)
            prefix=str(GAME/'Narrations/.studio/original_wav')+'%'
            total,relocated=db.execute('SELECT count(*),sum(wav LIKE ?) FROM clips WHERE status=?',(prefix,'decoded')).fetchone();db.close()
            if total and total==relocated:break
        except sqlite3.Error:pass
        time.sleep(20)
    config=GAME/'Narrations/.studio/pipeline_config.json'
    config.write_text(json.dumps(dict(game=str(GAME),catalog_root=str(GAME/'Narrations/.studio'),projects=str(GAME/'Narrations'))),encoding='utf8')
    env=dict(os.environ,F16_NARRATION_CONFIG=str(config))
    def command(script,*args):
        subprocess.run([sys.executable,str(ROOT/script),*args],env=env,cwd=ROOT,check=True,creationflags=0x08000000)
    command('pes_extract_library.py','publish')
    command('ingest_pes_library.py')
    voices=json.loads((ROOT/'pes_unique_assets.json').read_text(encoding='utf8'))['voices']
    report=[]
    for voice in voices:
        name=voice['narrator']
        try:
            command('base_matching.py',name)
            # Restore identity- and scene-specific layers after the broad
            # semantic pass so call names, formations and weather variants
            # survive the full-corpus profile rebuild.
            command('contextual_matching.py',name)
            command('match_club_names.py',name)
            # The CLI accepts every project, with no narrator-name whitelist.
            command('profiles.py',name)
            report.append(dict(narrator=name,state='built',review_required=True))
        except Exception as exc:report.append(dict(narrator=name,state='failed',error=str(exc)))
        (RAW/'profiles_progress.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report,ensure_ascii=True),flush=True)

if __name__=='__main__':run()
