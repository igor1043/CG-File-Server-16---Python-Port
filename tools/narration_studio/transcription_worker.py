"""Local ASR executable companion: selected audio or resumable project batch."""
import argparse,sys,json
from pathlib import Path
from core import connect,WORK,PROJECTS
from transcribe import whisper_model,export_text
from topics import topic

def main():
    p=argparse.ArgumentParser();p.add_argument('--table',choices=['clips','sources']);p.add_argument('--key');p.add_argument('--scope');p.add_argument('--library',action='store_true');p.add_argument('--project',default='Vilani');p.add_argument('--smoke',action='store_true');a=p.parse_args()
    if a.smoke:
        import faster_whisper,av,ctranslate2
        print('Local ASR dependencies OK');return
    if a.library:
        transcribe_library(a.project)
    elif a.scope:
        from transcribe_batch import run
        run(a.scope)
    else:
        db=connect();r=db.execute('SELECT * FROM '+a.table+' WHERE key=?',(a.key,)).fetchone()
        if r is None:raise ValueError('Áudio não encontrado.')
        model=whisper_model('small');path=r['wav'] if a.table=='clips' else r['path']
        segments,_=model.transcribe(path,language='pt',beam_size=5,vad_filter=False,condition_on_previous_text=False)
        segments=[s for s in segments if s.no_speech_prob<.6 and s.avg_logprob>-1]
        text=' '.join(s.text.strip() for s in segments) or '[sem fala detectada]'
        score=sum(s.avg_logprob for s in segments)/max(1,len(segments))
        if a.table=='clips':db.execute('UPDATE clips SET transcript=? WHERE wav=?',(text,path))
        else:db.execute('UPDATE sources SET transcript=?,confidence=?,topic=? WHERE key=?',(text,score,topic(r['event'],path,text),a.key))
        db.commit();export_text(db);db.close();print(text)
    from projects import save
    save(a.project)

def transcribe_library(name):
    db=connect();rows=db.execute('SELECT * FROM sources WHERE narrator=? ORDER BY path',(name,)).fetchall()
    model=None;done=0;failed=0;index=[]
    progress=WORK/('library_progress_'+name+'.json')
    def write_progress(state):
        temp=progress.with_suffix('.tmp');temp.write_text(json.dumps(dict(state=state,done=done,total=len(rows),failed=failed)),encoding='utf8');temp.replace(progress)
    write_progress('running')
    for row in rows:
        path=Path(row['path']);text=row['transcript'] or '';error=''
        try:
            if not text:
                if model is None:model=whisper_model('small')
                segments,_=model.transcribe(str(path),beam_size=5,vad_filter=True,condition_on_previous_text=False)
                segments=list(segments)
                if not segments:
                    segments,_=model.transcribe(str(path),beam_size=5,vad_filter=False,condition_on_previous_text=False)
                    segments=[s for s in segments if s.no_speech_prob<.6 and s.avg_logprob>-1]
                text=' '.join(s.text.strip() for s in segments) or '[sem fala detectada]'
                score=sum(s.avg_logprob for s in segments)/max(1,len(segments))
                db.execute('UPDATE sources SET transcript=?,confidence=?,topic=? WHERE key=?',(text,score,topic(row['event'],str(path),text),row['key']));db.commit()
            path.with_suffix(path.suffix+'.txt').write_text(text,encoding='utf8')
        except Exception as exc:failed+=1;error=str(exc)
        index.append(dict(audio=str(path),transcript=text,error=error));done+=1;write_progress('running')
    target=PROJECTS/name/'transcriptions/library.json';target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(index,ensure_ascii=False,indent=2),encoding='utf8')
    # Attached folders receive their own complete manifest as requested.
    folders=PROJECTS/name/'library_folders.json'
    if folders.exists():
        for folder in json.loads(folders.read_text(encoding='utf8')):
            root=Path(folder).expanduser().resolve()
            if not root.is_dir():continue
            items=[]
            for item in index:
                audio=Path(item['audio']).expanduser().resolve()
                try:audio.relative_to(root)
                except ValueError:continue
                items.append(item)
            (root/'transcriptions.json').write_text(json.dumps(items,ensure_ascii=False,indent=2),encoding='utf8')
    export_text(db);db.close();write_progress('complete')
    if failed:raise ValueError(str(failed)+' áudios precisam de revisão. Consulte library.json.')

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf8')
    main()
