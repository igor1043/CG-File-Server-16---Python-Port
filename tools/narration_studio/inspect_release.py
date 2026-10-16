from pathlib import Path
import json
import psutil

root=Path(__file__).resolve().parents[2]
for name in ('build_server_narration_cards.log','tools/narration_studio/build_studio_release.log','build/narration_studio_release/studio_startup.log','build/narration_studio_release/studio_smoke.json','build/narration_studio_release/studio_error.log'):
    path=root/name
    print(name,flush=True)
    if path.exists():print(path.read_text(encoding='utf8',errors='replace')[-800:],flush=True)
print('processes',flush=True)
for p in psutil.process_iter(['pid','name']):
    if p.info['name'].casefold() in ('fifa16.exe','server16python.exe','narrationstudio.exe'):
        print(json.dumps(p.info),flush=True)
