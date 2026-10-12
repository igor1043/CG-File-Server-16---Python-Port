"""Compare cached SPS duration/energy with its source; report speech gaps."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import hashlib,json,subprocess,tempfile,wave
import numpy as np
from core import connect,GAME,VGM,WORK,FFMPEG

def pcm_stats(path):
    result=subprocess.run([FFMPEG,'-v','error','-i',str(path),'-ac','1','-ar','16000','-f','f32le','-'],capture_output=True,check=True,creationflags=0x08000000)
    samples=np.frombuffer(result.stdout,dtype='<f4');duration=len(samples)/16000
    size=320;frames=np.pad(samples,(0,(-len(samples))%size)).reshape(-1,size)
    rms=np.sqrt((frames*frames).mean(axis=1));active=np.flatnonzero(rms>.006)
    return dict(duration=duration,peak=float(np.max(np.abs(samples))) if len(samples) else 0,active_ratio=float(len(active)/max(1,len(frames))),leading=(float(active[0])*.02 if len(active) else duration),trailing=(max(0,duration-float(active[-1]+1)*.02) if len(active) else duration))

def audit(narrator='Luiz Roberto'):
    db=connect();rows=[dict(r) for r in db.execute('SELECT DISTINCT s.* FROM mappings m JOIN sources s ON m.source=s.key WHERE m.profile=?',(narrator,))];db.close()
    def check(row):
        p=Path(row['path']);token=hashlib.sha256((str(p)+str(p.stat().st_mtime_ns)+'16000').encode()).hexdigest()[:24]
        source=pcm_stats(p);sps=GAME/'Narrations'/narrator/'encoded'/(token+'.sps')
        if not sps.exists():sps=Path(__import__('projects').folder(narrator))/'build/encoded'/(token+'.sps')
        with tempfile.TemporaryDirectory(prefix='narration_audit_') as folder:
            wav=Path(folder)/'decoded.wav';subprocess.run([str(VGM),'-i','-o',str(wav),str(sps)],capture_output=True,check=True,creationflags=0x08000000)
            decoded=pcm_stats(wav)
        issues=[]
        if abs(source['duration']-decoded['duration'])>.1:issues.append('duração alterada')
        if decoded['peak']<.002:issues.append('áudio silencioso')
        if source['leading']>.35:issues.append('silêncio inicial na fonte')
        if source['trailing']>.7:issues.append('silêncio final na fonte')
        return dict(path=str(p),transcript=row['transcript'],source=source,encoded=decoded,issues=issues)
    with ThreadPoolExecutor(max_workers=4) as pool:report=list(pool.map(check,rows))
    summary=dict(narrator=narrator,sources=len(report),duration_errors=sum('duração alterada' in r['issues'] for r in report),silent_encoded=sum('áudio silencioso' in r['issues'] for r in report),source_gaps=sum(bool(r['issues']) for r in report))
    destination=GAME/'Narrations'/narrator/'audio_quality_report.json';destination.write_text(json.dumps(dict(summary=summary,audio=report),ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(summary,ensure_ascii=False),flush=True)
    return report

if __name__=='__main__':audit()
