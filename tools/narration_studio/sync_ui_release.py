from pathlib import Path
import hashlib,json,shutil

root=Path(__file__).resolve().parents[2]
game=Path(r'U:\fifa 16'); release=game/'runtime/NarrationRelease'
manifest=release/'manifest.json'
data=json.loads(manifest.read_text(encoding='utf8'))
print('file_schema',data['files'][0],flush=True)
sources={'Server16Python.exe':game/'Server16Python.exe','cgfs16_overlay.dll':root/'bin/cgfs16_overlay.dll'}
for item in data['files']:
    name=Path(item['path']).name
    if name in sources:
        payload=release/item['path'];payload.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(sources[name],payload)
        item['sha256']=hashlib.sha256(payload.read_bytes()).hexdigest()
manifest.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
assert all(hashlib.sha256((release/item['path']).read_bytes()).hexdigest()==item['sha256'] for item in data['files'])
print('release_files_verified',len(data['files']),flush=True)
