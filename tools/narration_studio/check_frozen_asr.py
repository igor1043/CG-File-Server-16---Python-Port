"""Exercise the packaged AI with one recording and an isolated catalogue."""
from pathlib import Path
import tempfile,subprocess,os,json,shutil
from core import connect
root=Path(__file__).resolve().parents[2]
worker=root.parent/'build/portable_worker/TranscriptionWorker.exe'
with tempfile.TemporaryDirectory(prefix='f16_asr_test_') as temporary:
    folder=Path(temporary);audio=folder/'audio/recording.wav';audio.parent.mkdir()
    shutil.copy2(Path(__file__).parent/'preview.wav',audio)
    db=connect(folder/'catalog.sqlite')
    db.execute('INSERT INTO sources(key,narrator,path,event,topic) VALUES (?,?,?,?,?)',('test','Test',str(audio),'','Outros comentários'));db.commit();db.close()
    project=folder/'projects/Test';project.mkdir(parents=True)
    (project/'library_folders.json').write_text(json.dumps([str(audio.parent)]),encoding='utf8')
    config=folder/'config.json';config.write_text(json.dumps(dict(game=str(folder/'game'),catalog_root=str(folder),projects=str(folder/'projects'))),encoding='utf8')
    result=subprocess.run([str(worker),'--library','--project','Test'],env=dict(os.environ,F16_NARRATION_CONFIG=str(config)),capture_output=True,timeout=180,creationflags=0x08000000)
    if result.returncode:
        details=(project/'transcriptions/library.json').read_text(encoding='utf8') if (project/'transcriptions/library.json').exists() else ''
        raise AssertionError(result.stderr.decode('utf8',errors='replace')[-1500:]+'\n'+details)
    progress=json.loads((folder/'library_progress_Test.json').read_text())
    assert progress['state']=='complete' and progress['done']==1
    assert audio.with_suffix('.wav.txt').is_file() and (audio.parent/'transcriptions.json').is_file()
    print(json.dumps(dict(status='frozen_ai_transcribed_and_exported',text=audio.with_suffix('.wav.txt').read_text(encoding='utf8'))),flush=True)
