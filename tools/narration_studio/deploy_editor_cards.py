"""Publish checked local builds after FIFA/Server/editor have been closed."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import hashlib,json,shutil,psutil,os,subprocess
from PyInstaller.archive.readers import CArchiveReader

root=Path(__file__).resolve().parents[2]
game=Path(r'U:\fifa 16')
editor=Path(r'J:\mods\fifa 16\NarrationStudio')
blocking=[p.info for p in psutil.process_iter(['pid','name']) if p.info['name'].casefold() in ('fifa16.exe','server16python.exe','narrationstudio.exe')]
if blocking:raise RuntimeError('Feche os aplicativos antes de instalar: '+str(blocking))

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

archive=CArchiveReader(str(root/'dist/Server16Python.exe'))
for filename in ('cgfs16_overlay.dll','fifa16_narration.dll'):
    entry=next(n for n in archive.toc if n.replace('\\','/')=='bin/'+filename)
    assert hashlib.sha256(archive.extract(entry)).hexdigest()==digest(root/'bin'/filename)

stamp=datetime.now(timezone(timedelta(hours=-3))).strftime('%Y%m%d_%H%M%S')
backup=game/'runtime/backups'/('editor_cards_'+stamp);backup.mkdir(parents=True)
files=[(root/'dist/Server16Python.exe',game/'Server16Python.exe'),
       (root/'bin/cgfs16_overlay.dll',game/'runtime/cgfs16_overlay.dll'),
       (root/'bin/cgfs16_overlay.dll',root/'runtime/cgfs16_overlay.dll'),
       (root/'build/narration_studio_release/NarrationStudio.exe',editor/'NarrationStudio.exe')]
copied=[]
for index,(source,destination) in enumerate(files):
    assert source.is_file(),source
    destination.parent.mkdir(parents=True,exist_ok=True)
    if destination.exists():shutil.copy2(destination,backup/(str(index)+'_'+destination.name))
    temporary=destination.with_name(destination.name+'.new')
    shutil.copy2(source,temporary);temporary.replace(destination)
    assert digest(source)==digest(destination)
    copied.append(dict(path=str(destination),sha256=digest(destination)))

# Keep the existing, user-visible release installer consistent with this build.
release=game/'runtime/NarrationRelease'
manifest=release/'manifest.json'
if manifest.is_file():
    data=json.loads(manifest.read_text(encoding='utf8'))
    (backup/'release_manifest.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
    print('manifest_schema',list(data) if isinstance(data,dict) else 'list',flush=True)

env=dict(os.environ,F16_NARRATION_CONFIG=str(editor/'studio_config.json'))
result=subprocess.run([str(editor/'NarrationStudio.exe'),'--smoke'],cwd=editor,env=env,timeout=45,creationflags=0x08000000)
assert result.returncode==0
smoke=json.loads((editor/'studio_smoke.json').read_text(encoding='utf8'))
assert smoke['status']=='ok' and smoke['paired_rows']
report=dict(status='installed',backup=str(backup),files=copied,editor_paired=True,original_transcribed=smoke['counts']['transcribed'])
(game/'runtime/editor_cards_release_verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
