"""Resumable local Whisper transcription; results retain confidence for review."""
from pathlib import Path
import os, sys, ctypes, json, time, argparse
from core import connect, WORK, WHISPER_MODEL

def whisper_model(size='small'):
    model_path=WHISPER_MODEL if (WHISPER_MODEL/'model.bin').is_file() else Path(size)
    model=str(model_path)
    def create(**kwargs):
        from faster_whisper import WhisperModel
        try:return WhisperModel(model,local_files_only=True,**kwargs)
        except (OSError,FileNotFoundError):return WhisperModel(model,**kwargs)
    if getattr(sys,'frozen',False) or os.environ.get('F16_NARRATION_CPU')=='1':
        return create(device='cpu',compute_type='int8',cpu_threads=4)
    dll_dirs=[]
    if os.name=='nt':
        try:
            import nvidia.cublas
            path=Path(next(iter(nvidia.cublas.__path__)))/'bin'
            os.environ['PATH']=str(path)+os.pathsep+os.environ['PATH']
            dll_dirs.append(os.add_dll_directory(str(path)))
            ctypes.WinDLL(str(path/'cublas64_12.dll'))
        except (ImportError,OSError): pass
    from faster_whisper import WhisperModel
    try:
        model=create(device='cuda',compute_type='int8_float16')
        # Keep DLL directories alive for lazy inference initialization.
        model._narration_dll_dirs=dll_dirs
        return model
    except RuntimeError:
        return create(device='cpu',compute_type='int8',cpu_threads=4)

def run(scope='all',limit=0,model_size='small'):
    model=whisper_model(model_size)
    db=connect()
    jobs=[]
    if scope in ('all','original','matching'):
        additional=" AND b.active=1 AND (event LIKE '%GOAL%' OR event LIKE '%SHOT%' OR event LIKE '%SAVE%' OR event LIKE '%CORNER%' OR event LIKE '%FOUL%' OR event LIKE '%OFFSIDE%')" if scope=='matching' else ''
        grouping='event' if scope=='matching' else 'wav'
        jobs += [('clips',dict(r)) for r in db.execute('''SELECT c.*,b.active FROM clips c JOIN banks b ON c.bank=b.key
            WHERE transcript='' AND status='decoded' '''+additional+' GROUP BY '+grouping+'''
            ORDER BY (event='bINTRO_HELLO_SHORT') DESC,(event LIKE '%INTRO%' OR event LIKE '%HELLO%') DESC, active DESC, bank,offset''')]
    if scope in ('all','sources','Vilani','Luiz Roberto'):
        query="SELECT * FROM sources WHERE (transcript='' OR (transcript='[sem fala detectada]' AND duration=0)) AND error=''"
        params=[]
        if scope in ('Vilani','Luiz Roberto'): query+=' AND narrator=?';params=[scope]
        query+=" ORDER BY (event LIKE '%INTRO%' OR event LIKE '%HELLO%' OR event LIKE '%GOAL%' OR path LIKE '%40_MAIN%') DESC, narrator,path"
        jobs += [('sources',dict(r)) for r in db.execute(query,params)]
    if scope=='Luiz Roberto':
        # The PES library starts with hundreds of identical 130 ms fillers.
        # Prioritize complete commentary recordings for the test profile.
        jobs.sort(key=lambda job:(any(t in job[1]['path'] for t in ('30_MAIN','40_MAIN')),Path(job[1]['path']).stat().st_size),reverse=True)
    if limit: jobs=jobs[:limit]
    print('Whisper jobs',len(jobs),'scope',scope,flush=True)
    done=0;failed=0
    def progress(state):
        dest=WORK/f'transcribe_{scope.replace(" ","_")}_progress.json'
        tmp=dest.with_suffix('.tmp');tmp.write_text(json.dumps(dict(scope=scope,state=state,done=done,total=len(jobs),failed=failed,model=model_size,updated=time.time()),indent=2),encoding='utf8');tmp.replace(dest)
    progress('running')
    for table,item in jobs:
        path=item['wav'] if table=='clips' else item['path']
        try:
            segments,info=model.transcribe(path,language='pt',beam_size=5,condition_on_previous_text=False,
                vad_filter=True,initial_prompt='Narração de futebol brasileiro. Gol. Escanteio. Ronaldinho. Tiago Leifert. Luiz Roberto. Gustavo Villani. Caio Ribeiro.')
            segments=list(segments)
            if not segments and info.duration>0.6:
                # Silero rejects some correctly decoded PES speech. Retry
                # using Whisper's own silence detection before declaring it
                # silent; short placeholder sounds are not retried.
                segments,info=model.transcribe(path,language='pt',beam_size=5,condition_on_previous_text=False,vad_filter=False)
                segments=[s for s in segments if s.no_speech_prob<0.6 and s.avg_logprob>-1.0]
            text=' '.join(s.text.strip() for s in segments).strip()
            confidence=sum(s.avg_logprob for s in segments)/max(1,len(segments))
            if not text: text='[sem fala detectada]'
            if table=='clips':
                db.execute('UPDATE clips SET transcript=? WHERE wav=?',(text,path))
            else:
                db.execute('UPDATE sources SET transcript=?,confidence=?,duration=? WHERE key=?',(text,confidence,info.duration,item['key']))
            db.commit()
            done+=1
            if done%5==0:progress('running')
            if done%20==0:
                db.commit(); export_text(db);print(f'transcribe {done}/{len(jobs)} {table}: {text}',flush=True)
        except Exception as exc:
            db.execute(f'UPDATE {table} SET error=? WHERE key=?',(str(exc),item['key']))
            db.commit(); print('transcribe error',path,str(exc),flush=True)
            failed+=1
    db.commit();export_text(db);db.close();progress('complete')

def export_text(db):
    out=WORK/'transcriptions';out.mkdir(exist_ok=True)
    for (narrator,) in db.execute('SELECT DISTINCT narrator FROM sources'):
        rows=db.execute("SELECT path,transcript,confidence FROM sources WHERE narrator=? AND transcript!=''",(narrator,))
        text='\n'.join(f"{r['path']}\t{float(r['confidence'] or 0):.3f}\t{r['transcript']}" for r in rows)
        (out/(narrator+'.txt')).write_text(text,encoding='utf8')
    rows=db.execute("SELECT key,event,transcript FROM clips WHERE transcript!=''")
    (out/'Tiago Leifert.txt').write_text('\n'.join(f"{r['key']}\t{r['event']}\t{r['transcript']}" for r in rows),encoding='utf8')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--scope',default='all');p.add_argument('--limit',type=int,default=0);p.add_argument('--model',default='small');a=p.parse_args();run(a.scope,a.limit,a.model)
