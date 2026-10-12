"""Resumable lossless PES library extraction with per-recording transcripts.

Encoded duplicates share a physical FLAC through NTFS hard links. Source IDs
are provenance only: they are never interpreted as FIFA event IDs.
"""
from pathlib import Path
import argparse, json, sqlite3, hashlib, os, time,subprocess,tempfile
from concurrent.futures import ThreadPoolExecutor
from pes_archives import decode_frames,audio_header

DEFAULT_ROOT=Path(r'J:\mods\fifa 16\audios narradores')
WORK=Path(__file__).parent

def open_index(root):
    root.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(root/'library.sqlite',timeout=60)
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('CREATE TABLE IF NOT EXISTS assets (sha TEXT PRIMARY KEY,path TEXT,duration REAL,peak REAL,status TEXT,error TEXT,transcript TEXT DEFAULT NULL)')
    db.commit()
    return db

def extract(root=DEFAULT_ROOT,workers=4):
    import numpy as np
    import av
    db=open_index(root)
    inventory=json.loads((WORK/'pes_unique_assets.json').read_text(encoding='utf8'))
    assets=inventory['unique']
    for voice in inventory['voices']:
        original=root/voice['narrator']/'original';original.mkdir(parents=True,exist_ok=True)
        (original/'LEIA-ME.txt').write_text('Áudios completos extraídos dos bancos PES. Os identificadores preservam a origem e não correspondem aos eventos FIFA. A extração e transcrição são retomáveis; acompanhe progress.json na raiz da biblioteca.',encoding='utf8')
    ready={r[0] for r in db.execute("SELECT sha FROM assets WHERE status IN ('decoded','empty')")}
    assets.sort(key=lambda r:('MAIN' not in r['bank'] and 'ADD' not in r['bank'],r['archive'],r['offset']))
    pending=[r for r in assets if r['sha256'] not in ready]
    poolroot=root/'.assets';poolroot.mkdir(exist_ok=True)
    def decode(ref):
        token=ref['sha256'];target=poolroot/token[:2]/(token+'.flac');target.parent.mkdir(exist_ok=True)
        try:
            with Path(ref['archive']).open('rb') as inp:
                inp.seek(ref['offset']);data=inp.read(ref['size'])
            if hashlib.sha256(data).hexdigest()!=token:raise ValueError('Arquivo de origem mudou')
            try:frames,header=decode_frames(data)
            except Exception:
                # vgmstream handles game-specific ADX/HCA variants which the
                # general decoder rejects; retain the same duration check.
                from core import VGM
                with tempfile.TemporaryDirectory(prefix='f16_pes_') as temporary:
                    directory=Path(temporary);header=audio_header(data)
                    raw=directory/('source.'+('hca' if header['codec']=='hca' else 'adx'))
                    raw.write_bytes(data);wav=directory/'decoded.wav'
                    result=subprocess.run([str(VGM),'-i','-o',str(wav),str(raw)],capture_output=True,timeout=120,creationflags=0x08000000)
                    if result.returncode or not wav.exists():raise ValueError('vgmstream não conseguiu decodificar: '+result.stderr.decode(errors='replace')[-300:])
                    with av.open(str(wav)) as inp:frames=list(inp.decode(audio=0))
                    actual=sum(f.samples for f in frames);rate=frames[0].sample_rate
                    if header['duration'] is not None and abs(actual/rate-header['duration'])>.05:raise ValueError('Duração divergente no decoder alternativo')
                    header.update(decoded_samples=actual,rate=rate,duration=actual/rate)
            frames=[frame for frame in frames if frame.samples]
            if not frames:return (token,'',0,0,'empty','')
            peak=max(float(np.max(np.abs(f.to_ndarray().astype('float64')))) for f in frames)
            temp=target.with_suffix('.tmp')
            with av.open(str(temp),'w',format='flac') as out:
                stream=out.add_stream('flac',rate=frames[0].sample_rate);stream.layout=frames[0].layout
                for frame in frames:
                    for packet in stream.encode(frame):out.mux(packet)
                for packet in stream.encode(None):out.mux(packet)
            # Verify the complete recording survives the output conversion.
            with av.open(str(temp)) as inp:
                actual=sum(f.samples for f in inp.decode(audio=0))
            if actual!=header['decoded_samples']:raise ValueError('Conversão alterou quantidade de amostras')
            temp.replace(target)
            return (token,str(target),header['duration'],peak,'decoded','')
        except Exception as exc:return (token,'',0,0,'failed',str(exc))
    started=time.time()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        # Bounded batches keep 200k futures and decoded frames out of RAM.
        for start in range(0,len(pending),128):
            for result in pool.map(decode,pending[start:start+128]):
                db.execute('INSERT INTO assets (sha,path,duration,peak,status,error) VALUES (?,?,?,?,?,?) ON CONFLICT(sha) DO UPDATE SET path=excluded.path,duration=excluded.duration,peak=excluded.peak,status=excluded.status,error=excluded.error',result)
            db.commit()
            progress=dict(state='extracting',processed=len(ready)+min(start+128,len(pending)),total=len(assets),elapsed=round(time.time()-started))
            (root/'progress.json').write_text(json.dumps(progress),encoding='utf8')
            print(json.dumps(progress),flush=True)
    publish(root,db)
    db.close()

def publish(root,db):
    lookup={r[0]:r[1:] for r in db.execute('SELECT sha,path,transcript,status FROM assets')}
    folders={}
    for index in (WORK.parent.parent.parent/'narrações fifa').glob('*/indexes/pes_references.json'):
        refs=json.loads(index.read_text(encoding='utf8'))
        for ref in refs:
            path,text,status=lookup.get(ref['sha256'],('',None,'pending'))
            dest=root/ref['narrator']/'original'/ref['bank']
            if dest not in folders:
                dest.mkdir(parents=True,exist_ok=True)
                with os.scandir(dest) as files:folders[dest]={entry.name for entry in files}
            stem=str(ref['id'])+'_'+str(ref['index'])
            if path:
                audio=dest/(stem+'.flac')
                if audio.name not in folders[dest]:os.link(path,audio);folders[dest].add(audio.name)
                ref['audio']=str(audio)
            ref['extraction_status']=status
            if text is not None and stem+'.txt' not in folders[dest]:
                (dest/(stem+'.txt')).write_text(text,encoding='utf8');folders[dest].add(stem+'.txt')
        target=root/refs[0]['narrator']/'index.json' if refs else None
        if target:
            target.write_text(json.dumps(refs,ensure_ascii=False,separators=(',',':')),encoding='utf8')
            print(json.dumps(dict(narrator=refs[0]['narrator'],available=sum('audio' in ref for ref in refs),references=len(refs))),flush=True)

def transcribe(root=DEFAULT_ROOT):
    from transcribe import whisper_model
    db=open_index(root);model=whisper_model('small');done=0
    while True:
        rows=db.execute("SELECT sha,path,duration,peak FROM assets WHERE status='decoded' AND transcript IS NULL ORDER BY duration DESC LIMIT 100").fetchall()
        if not rows:
            state=json.loads((root/'progress.json').read_text()) if (root/'progress.json').exists() else {}
            if state.get('state')=='complete':break
            time.sleep(5);continue
        for sha,path,duration,peak in rows:
            try:
                text='[sem fala detectada]'
                if peak>0 and duration>.25:
                    segments,info=model.transcribe(path,beam_size=5,vad_filter=True,condition_on_previous_text=False)
                    parts=list(segments)
                    if not parts and duration>.6:
                        segments,info=model.transcribe(path,beam_size=5,vad_filter=False,condition_on_previous_text=False)
                        parts=[s for s in segments if s.no_speech_prob<.6 and s.avg_logprob>-1]
                    text=' '.join(s.text.strip() for s in parts).strip() or text
                db.execute('UPDATE assets SET transcript=? WHERE sha=?',(text,sha));db.commit();done+=1
                # Sidecar of pooled asset is immediately available; per-ID
                # copies are published periodically without duplicating audio.
                Path(path).with_suffix('.txt').write_text(text,encoding='utf8')
                if done%100==0:print('Transcritos:',done,flush=True)
            except Exception as exc:
                print('Falha de transcrição:',sha,str(exc),flush=True)
                db.execute("UPDATE assets SET status='transcription_failed',error=? WHERE sha=?",(str(exc),sha));db.commit()
        if done%1000==0:publish(root,db)
    publish(root,db);db.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['extract','transcribe','publish']);parser.add_argument('--root',type=Path,default=DEFAULT_ROOT)
    args=parser.parse_args()
    if args.action=='extract':
        extract(args.root)
        state=json.loads((args.root/'progress.json').read_text());state['state']='complete'
        (args.root/'progress.json').write_text(json.dumps(state),encoding='utf8')
    elif args.action=='transcribe':transcribe(args.root)
    else:
        db=open_index(args.root);publish(args.root,db);db.close()
