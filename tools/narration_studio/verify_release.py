"""Check the deployed Server archive against the built native modules."""
from pathlib import Path
import hashlib,json
from PyInstaller.archive.readers import CArchiveReader

PROJECT=Path(__file__).resolve().parents[2]
GAME=Path(r'U:\fifa 16')

def digest(data):return hashlib.sha256(data).hexdigest()

def verify():
    built=PROJECT/'dist/Server16Python.exe'
    installed=GAME/'Server16Python.exe'
    assert digest(built.read_bytes())==digest(installed.read_bytes()),'Installed EXE differs from this build'
    archive=CArchiveReader(str(installed))
    modules={}
    for filename in ('cgfs16_overlay.dll','fifa16_narration.dll'):
        name=next(n for n in archive.toc if n.replace('\\','/')=='bin/'+filename)
        actual=digest(archive.extract(name))
        assert actual==digest((PROJECT/'bin'/filename).read_bytes()),'Bundled DLL differs: '+filename
        modules[filename]=actual
    result=dict(executable=str(installed),sha256=digest(installed.read_bytes()),native_modules=modules,status='verified')
    (GAME/'runtime/narration_release_verification.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps(result,indent=2))

if __name__=='__main__':verify()
