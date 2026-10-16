from pathlib import Path
import json,sqlite3,psutil,wave
game=Path(r'U:\fifa 16');raw=Path(r'J:\mods\fifa 16\audios narradores')
for root in (game,game/'Narrations/.studio',Path(r'J:\mods\fifa 16\NarrationStudio')):
    for name in ('studio_error.log','studio_startup.log','studio_config.json','catalog_ready.json'):
        path=root/name
        if path.exists():print(str(path),path.read_text(encoding='utf8',errors='replace')[-6000:])
for name in ('progress.json','profiles_progress.json'):
    path=raw/name
    if path.exists():print(str(path),path.read_text(encoding='utf8')[-2500:])
db=sqlite3.connect(game/'Narrations/.studio/catalog.sqlite')
for row in db.execute("SELECT wav FROM clips WHERE status='decoded' LIMIT 5"):
    path=Path(row[0]);print('original',str(path),path.exists())
    if path.exists():
        with wave.open(str(path)) as audio:print('wav',audio.getparams())
for process in psutil.process_iter(['pid','name','cmdline']):
    args=process.info['cmdline'] or []
    if any(any(token in arg for token in ('finalize_pes','export_existing','prepare_portable','pes_extract')) for arg in args):print('process',json.dumps(process.info))
