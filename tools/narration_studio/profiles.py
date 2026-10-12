"""Compile reversible native payloads without rewriting game archives."""
from __future__ import annotations
from pathlib import Path
import json, struct, subprocess, wave, hashlib, collections, re
from concurrent.futures import ThreadPoolExecutor,as_completed
from core import connect, GAME, TOOL, SX, VGM, WORK,FFMPEG

ROOT=GAME/'Narrations'

def assign(profile, clip, source, method='manual', score=1):
    db=connect()
    if not db.execute('SELECT 1 FROM clips WHERE key=?',(clip,)).fetchone(): raise ValueError('Áudio original inexistente')
    if not db.execute('SELECT 1 FROM sources WHERE key=?',(source,)).fetchone(): raise ValueError('Áudio fonte inexistente')
    # Aliases share the same physical sound in FIFA. Keep their assignments
    # consistent instead of silently selecting conflicting recordings.
    row=db.execute('SELECT bank,offset FROM clips WHERE key=?',(clip,)).fetchone()
    for alias in db.execute('SELECT key FROM clips WHERE bank=? AND offset=?',tuple(row)).fetchall():
        db.execute('INSERT OR REPLACE INTO mappings VALUES (?,?,?,?,?)',(profile,alias['key'],source,method,score))
    db.commit();db.close()

def seed_vilani():
    db=connect()
    # Same event and same variation; never infer player IDs from file order.
    db.execute('''INSERT OR IGNORE INTO mappings
        SELECT 'Vilani',c.key,s.key,'event_variant',1 FROM clips c JOIN sources s
        ON c.event=s.event AND c.row=s.variant WHERE s.narrator='Vilani'
        GROUP BY c.key ORDER BY s.path''')
    # Known introductory event changed name between source and target game.
    src=db.execute("SELECT key FROM sources WHERE narrator='Vilani' AND event='bINTRO_SEQ1_COMMENTATORS_STITCH' AND variant=0 ORDER BY path LIMIT 1").fetchone()
    if src:
        for c in db.execute("SELECT key FROM clips WHERE event='bINTRO_HELLO_SHORT'").fetchall():
            db.execute('INSERT OR REPLACE INTO mappings VALUES (?,?,?,?,?)',('Vilani',c['key'],src['key'],'intro_test',0.8))
    db.commit();db.close()

def encoded(source, destination, bitrate=16000, fallback=None):
    p=Path(source);destination.mkdir(parents=True,exist_ok=True)
    token=hashlib.sha256((str(p)+str(p.stat().st_mtime_ns)+str(bitrate)).encode()).hexdigest()[:24]
    sps=destination/(token+'.sps')
    if sps.exists(): return sps.read_bytes()
    if fallback is not None:
        cached=Path(fallback)/(token+'.sps')
        if cached.exists():return cached.read_bytes()
    wav=destination/(token+'.wav')
    subprocess.run([FFMPEG,'-hide_banner','-loglevel','error','-y','-i',str(p),'-ac','1','-ar','32000','-c:a','pcm_s16le',str(wav)],check=True,capture_output=True,timeout=120,creationflags=0x08000000)
    result=subprocess.run([str(SX),'-sndplayer','-fileformatversion1','-easpeex',f'-cbr{bitrate}','-playlocram','-rs32000','-noprogress','-v1',str(wav),f'-={token}'],cwd=destination,capture_output=True,timeout=120,creationflags=0x08000000)
    if result.returncode or not sps.exists(): raise ValueError(result.stdout.decode(errors='replace')+result.stderr.decode(errors='replace'))
    verify=destination/(token+'.verify.wav')
    decoded=subprocess.run([str(VGM),'-i','-o',str(verify),str(sps)],capture_output=True,timeout=60,creationflags=0x08000000)
    if decoded.returncode or not verify.exists(): raise ValueError('SPS gerado não decodifica')
    with wave.open(str(verify)) as w: actual=w.getnframes()/w.getframerate()
    with wave.open(str(wav)) as w: expected=w.getnframes()/w.getframerate()
    if abs(actual-expected)>0.1: raise ValueError('Duração codificada não corresponde à fonte')
    wav.unlink();verify.unlink();return sps.read_bytes()

def compile_profile(name, limit=0, destination=None):
    db=connect(); dest=Path(destination) if destination else ROOT/name; dest.mkdir(parents=True,exist_ok=True)
    rows=db.execute('''SELECT c.*,b.name AS bank_name,b.active,s.path,s.transcript AS source_transcript,m.method,m.score FROM mappings m
        JOIN clips c ON m.clip=c.key JOIN banks b ON b.key=c.bank JOIN sources s ON s.key=m.source WHERE m.profile=? AND b.active=1
        ORDER BY (c.event='bINTRO_HELLO_SHORT') DESC, m.score DESC,c.bank,c.offset''',(name,)).fetchall()
    if limit: rows=rows[:limit]
    paths=sorted({row['path'] for row in rows});assets={};errors={}
    progress=dest/'build_progress.json'
    def write_progress(done,state='encoding'):
        temporary=progress.with_suffix('.tmp')
        temporary.write_text(json.dumps(dict(profile=name,state=state,encoded=done,total_sources=len(paths),occurrences=len(rows),failed_sources=len(errors)),indent=2),encoding='utf8');temporary.replace(progress)
    write_progress(0)
    # Conversion is independent for each source. Keep a small bounded pool
    # while FIFA and local transcription may be running at the same time.
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs={pool.submit(encoded,path,dest/'encoded',fallback=ROOT/name/'encoded'):path for path in paths}
        for i,future in enumerate(as_completed(jobs),1):
            path=jobs[future]
            try:assets[path]=future.result()
            except Exception as exc:errors[path]=str(exc)
            if i%20==0 or i==len(paths):write_progress(i);print(f'encode {name} {i}/{len(paths)} failed={len(errors)}',flush=True)
    banks=collections.defaultdict(dict);report=[]
    for row in rows:
        try:
            if row['path'] in errors:raise ValueError(errors[row['path']])
            payload=assets[row['path']]
            # WAV names retain the original OFF value, before any 'slot'
            # wrapper was skipped for decoding.
            offset=int(Path(row['wav']).stem,16)
            bank='audiodata/speechdata/por_br/'+row['bank_name'].lower()+'.sbs'
            previous=banks[bank].get(offset)
            if previous is not None and previous!=payload:
                raise ValueError('Ocorrência compartilha o áudio com outra associação diferente; revise as variantes.')
            banks[bank][offset]=payload
            stat=Path(row['path']).stat()
            report.append(dict(clip=row['key'],event=row['event'],source=row['path'],source_signature=dict(size=stat.st_size,mtime_ns=stat.st_mtime_ns),transcript=row['source_transcript'],mode='resident_sps',bytes=len(payload),original_bytes=row['capacity'],original_duration=row['duration']))
        except Exception as exc: report.append(dict(clip=row['key'],source=row['path'],error=str(exc)))
    def u32(n):return struct.pack('<I',n)
    unique={};pooled=[]
    for samples in banks.values():
        for payload in samples.values():
            token=hashlib.sha256(payload).digest()
            if token not in unique:unique[token]=len(pooled);pooled.append(payload)
    # Full recordings appear once; bank occurrences only reference an asset.
    # This changes memory use, never the duration or samples of the recording.
    out=bytearray(b'F16NPK3\0'+u32(len(pooled)))
    for payload in pooled:out+=u32(len(payload))+payload
    out+=u32(len(banks))
    for path,samples in sorted(banks.items()):
        text=path.encode('utf-16le');out+=u32(len(text)//2)+text+u32(len(samples))
        for off,payload in sorted(samples.items()):
            if len(payload)>64*1024*1024:raise ValueError('Uma gravação excede o limite de memória de 64 MiB por áudio')
            out+=struct.pack('<QI',off,unique[hashlib.sha256(payload).digest()])
    if len(out)>512*1024*1024:raise ValueError('Pacote excede o limite de memória de 512 MiB')
    package=dest/'profile.npack';temp=package.with_suffix('.tmp');temp.write_bytes(out);temp.replace(package)
    applied=sum('error' not in r for r in report)
    commentator='Caio Ribeiro'
    meta=dest/'profile.json'
    if meta.exists():commentator=json.loads(meta.read_text(encoding='utf8')).get('commentator',commentator)
    text_meta=dest/'narrator.txt'
    if text_meta.exists():
        values=dict(line.split('=',1) for line in text_meta.read_text(encoding='utf-8-sig').splitlines() if '=' in line)
        commentator=values.get('Comentarista',commentator).strip()
    summary=dict(name=name,commentator=commentator,version=3,package='profile.npack',mapped=applied,physical=sum(len(v) for v in banks.values()),unique_audio=len(pooled),failed=len(report)-applied,original_fallback=True,notes='Áudios completos em memória; falas sem associação usam o FIFA instalado.')
    if meta.exists():
        existing=json.loads(meta.read_text(encoding='utf8'))
        for key in ('competitions','portrait','gender_policy'):
            if key in existing:summary[key]=existing[key]
    (dest/'narrator.txt').write_text(f'Narrador={name}\nComentarista={commentator}\nPacote=profile.npack\nVersao=3\n',encoding='utf8')
    (dest/'profile.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf8')
    (dest/'build_report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf8')
    lines=[]
    for row in rows:
        lines.extend((f"Ocorrência: {row['key']}",f"Tópico: {row['topic']}",f"Evento: {row['event']}",f"Original: {row['wav']}",f"Transcrição original: {row['transcript'] or '[pendente]'}",f"Substituição: {row['path']}",f"Transcrição nova: {row['source_transcript'] or '[pendente]'}",f"Método: {row['method']} · confiança: {row['score']:.3f}",''))
    (dest/'associations.txt').write_text('\n'.join(lines),encoding='utf8')
    write_progress(len(paths),'complete')
    db.close();print(summary,flush=True);return package

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('name',choices=['Tiago Leifert','Vilani','Luiz Roberto']);p.add_argument('--limit',type=int,default=0);a=p.parse_args()
    compile_profile(a.name,a.limit)
