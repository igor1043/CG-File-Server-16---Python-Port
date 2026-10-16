from pathlib import Path
import shutil,hashlib,json,subprocess,os,time
root=Path(__file__).resolve().parents[2];game=Path(r'U:\fifa 16')
built=root/'build/portable_editor/NarrationStudio.exe';dest=game/'NarrationStudio.exe'
worker=root.parent/'build/portable_worker/TranscriptionWorker.exe'
result=subprocess.run([str(worker),'--smoke'],capture_output=True,timeout=60,creationflags=0x08000000)
if result.returncode:raise RuntimeError(result.stderr.decode(errors='replace')[-1000:])
print(result.stdout.decode(errors='replace').strip(),flush=True)
if dest.exists():
    backup=game/'runtime/backups'/('studio_'+str(int(time.time())))
    backup.mkdir(parents=True,exist_ok=True);shutil.copy2(dest,backup/dest.name)
shutil.copy2(built,dest)
expected=hashlib.sha256(built.read_bytes()).hexdigest();actual=hashlib.sha256(dest.read_bytes()).hexdigest()
assert expected==actual
result=subprocess.run([str(dest),'--smoke'],capture_output=True,timeout=40,creationflags=0x08000000)
assert result.returncode==0,result.stderr.decode(errors='replace')[-1000:]
report=json.loads((game/'studio_smoke.json').read_text(encoding='utf8'))
assert report['paired_rows'] and report['status']=='ok'
print(json.dumps(dict(path=str(dest),sha256=actual,rows=report['original_rows'],catalog=report['catalog'])),flush=True)
