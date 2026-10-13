"""Resumable local transcription with independent chunks batched on the GPU."""
from pathlib import Path
import argparse,json,time,sys
import numpy as np
from core import connect,WORK
from topics import topic
from transcribe import whisper_model,export_text

def jobs_for(db,scope):
    source_pending="(transcript='' OR (transcript='[sem fala detectada]' AND duration=0)) AND error=''"
    original_pending="transcript='' AND status='decoded'"
    jobs=[]
    if scope=='Luiz_complete':
        rows=db.execute('SELECT * FROM sources WHERE '+source_pending+" AND narrator='Luiz Roberto' ORDER BY event,variant,path").fetchall()
        jobs.extend(('sources',dict(r)) for r in rows)
    if scope=='Vilani_complete':
        priority_topics=('Nomes de clubes','Campeonatos e competições','Estádios e cidades','Comentários de clubes')
        rows=db.execute('SELECT * FROM sources WHERE '+source_pending+" AND narrator='Vilani' ORDER BY CASE WHEN topic='Call names de jogadores' THEN 0 WHEN topic IN ("+','.join('?' for _ in priority_topics)+") THEN 1 WHEN event LIKE '%FORMATION%' OR event LIKE '%WEATHER%' OR event LIKE '%RAIN%' OR event LIKE '%SNOW%' THEN 2 ELSE 3 END,event,variant,path",priority_topics).fetchall()
        jobs.extend(('sources',dict(r)) for r in rows)
    if scope=='generic_sources':
        events=('bINTRO_SEQ1_GENERIC','bINTRO_SEQ2_GENERIC','bINTRO_SEQ1_COMMENTATORS_STITCH','bINTRO_SEQ1_WELCOME_STITCH','bINTRO_SEQ1_WRAP_UP','bTS_TEAM_INTRO')
        rows=db.execute('SELECT * FROM sources WHERE '+source_pending+" AND narrator='Vilani' AND event IN ("+','.join('?' for _ in events)+') ORDER BY event,variant,path',events).fetchall()
        jobs.extend(('sources',dict(r)) for r in rows)
    if scope in ('all','Luiz Roberto'):
        rows=db.execute('SELECT * FROM sources WHERE '+source_pending+" AND narrator='Luiz Roberto' AND topic NOT IN ('Call names de jogadores','Nomes de clubes') ORDER BY path").fetchall()
        jobs.extend(('sources',dict(r)) for r in rows)
    if scope in ('all','original_events'):
        rows=db.execute('SELECT * FROM clips WHERE '+original_pending+" AND topic NOT IN ('Call names de jogadores','Nomes de clubes') GROUP BY event ORDER BY event").fetchall()
        jobs.extend(('clips',dict(r)) for r in rows)
    if scope in ('all','Vilani'):
        rows=db.execute('SELECT s.* FROM sources s WHERE '+source_pending+" AND narrator='Vilani' AND topic NOT IN ('Call names de jogadores','Nomes de clubes') GROUP BY event ORDER BY event").fetchall()
        jobs.extend(('sources',dict(r)) for r in rows)
        rows=db.execute('SELECT s.* FROM sources s WHERE '+source_pending+" AND narrator='Vilani' AND key IN (SELECT source FROM mappings WHERE profile='Vilani') ORDER BY path").fetchall()
        jobs.extend(('sources',dict(r)) for r in rows)
    if scope in ('all','original'):
        rows=db.execute('SELECT * FROM clips WHERE '+original_pending+' GROUP BY wav ORDER BY (category=\'callname\'),event,wav').fetchall()
        jobs.extend(('clips',dict(r)) for r in rows)
    if scope=='all':
        rows=db.execute('SELECT * FROM sources WHERE '+source_pending+" AND topic NOT IN ('Call names de jogadores','Nomes de clubes') ORDER BY narrator,event,path").fetchall()
        jobs.extend(('sources',dict(r)) for r in rows)
    elif scope not in ('original','original_events','Luiz Roberto','Vilani','generic_sources','Vilani_complete','Luiz_complete'):
        rows=db.execute('SELECT * FROM sources WHERE '+source_pending+' AND narrator=? ORDER BY path',(scope,)).fetchall()
        jobs.extend(('sources',dict(r)) for r in rows)
    seen=set();result=[]
    for table,row in jobs:
        key=(table,row['wav'] if table=='clips' else row['key'])
        if key not in seen:result.append((table,row));seen.add(key)
    return result

def run(scope='all',limit=0,batch_size=8):
    from faster_whisper import BatchedInferencePipeline
    from faster_whisper.audio import decode_audio
    db=connect();jobs=jobs_for(db,scope)
    if limit:jobs=jobs[:limit]
    pipeline=BatchedInferencePipeline(model=whisper_model('small'))
    done=failed=0;started=time.time()
    output=WORK/('transcribe_batch_progress.json' if scope=='all' else 'transcribe_batch_'+scope.replace(' ','_')+'_progress.json')
    def progress(state):
        tmp=output.with_suffix('.tmp');tmp.write_text(json.dumps(dict(state=state,scope=scope,done=done,total=len(jobs),failed=failed,elapsed_seconds=round(time.time()-started)),indent=2),encoding='utf8');tmp.replace(output)
    def save(table,item,text,confidence,duration):
        if table=='clips':db.execute('UPDATE clips SET transcript=? WHERE wav=?',(text,item['wav']))
        else:db.execute('UPDATE sources SET transcript=?,confidence=?,duration=?,topic=? WHERE key=?',(text,confidence,duration,topic(item['event'],item['path'],text),item['key']))
    progress('running');print('Batched Whisper jobs',len(jobs),scope,flush=True)
    for start in range(0,len(jobs),batch_size):
        batch=jobs[start:start+batch_size];waves=[];timestamps=[];intervals=[];cursor=0
        for table,item in batch:
            path=item['wav'] if table=='clips' else item['path']
            try:
                audio=decode_audio(path,sampling_rate=16000);duration=len(audio)/16000
                if not len(audio) or duration<.18 or float(np.max(np.abs(audio)))<.002:
                    save(table,item,'[sem fala detectada]',0,duration);done+=1;continue
                begin=cursor;end=cursor+len(audio)
                intervals.append((begin/16000,end/16000,table,item,duration))
                for offset in range(begin,end,29*16000):timestamps.append(dict(start=offset/16000,end=min(end,offset+29*16000)/16000))
                waves.append(audio);waves.append(np.zeros(1600,dtype=np.float32));cursor=end+1600
            except Exception as exc:
                db.execute('UPDATE '+table+' SET error=? WHERE key=?',(str(exc),item['key']));failed+=1
        if intervals:
            try:
                segments,_=pipeline.transcribe(np.concatenate(waves),language='pt',beam_size=3,condition_on_previous_text=False,vad_filter=False,clip_timestamps=timestamps,batch_size=batch_size)
                words=[[] for _ in intervals];confidences=[[] for _ in intervals]
                for segment in segments:
                    if segment.no_speech_prob>=.6 or segment.avg_logprob< -1.:continue
                    for i,(begin,end,*_) in enumerate(intervals):
                        if begin-.005<=segment.start<end:
                            words[i].append(segment.text.strip());confidences[i].append(segment.avg_logprob);break
                for i,(_,_,table,item,duration) in enumerate(intervals):
                    text=' '.join(words[i]).strip() or '[sem fala detectada]'
                    score=sum(confidences[i])/max(1,len(confidences[i]));save(table,item,text,score,duration);done+=1
            except Exception as exc:
                # Leave failed inference jobs pending for a smaller batch on
                # the next run. File decode failures are recorded separately.
                print('Inference batch failed:',str(exc),flush=True);failed+=len(intervals)
        db.commit();progress('running')
        if done%200<batch_size:
            export_text(db);print(f'batch {done}/{len(jobs)} failed={failed}',flush=True)
    export_text(db);progress('complete');db.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--scope',default='all');p.add_argument('--limit',type=int,default=0);p.add_argument('--batch-size',type=int,default=8);a=p.parse_args();run(a.scope,a.limit,a.batch_size)
