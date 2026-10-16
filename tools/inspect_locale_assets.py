from pathlib import Path
import sys,json,hashlib,struct,datetime
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server16_py.narration_bank import BigArchive
game=Path(r'U:\fifa 16')
for p in (game/'data/loc').glob('*'):
    if p.suffix in ('.db','.big'):
        with p.open('rb') as f:head=f.read(128)
        print(json.dumps(dict(path=str(p),bytes=p.stat().st_size,modified=datetime.datetime.fromtimestamp(p.stat().st_mtime).isoformat(),head=head.hex())),flush=True)
for p in [game/'data/loc/locale.big',*game.glob('*.big')]:
    try:
        big=BigArchive(p)
        entries=[e for e in big.entries if ('por_br' in e.name.lower() or 'eng_us' in e.name.lower()) and ('loc' in e.name.lower() or e.name.lower().endswith('.db'))]
        for e in entries:
            data=big.read(e)
            print('archive',str(p),e.name,len(data),hashlib.sha256(data).hexdigest(),flush=True)
    except Exception as exc:print('archive_error',p.name,str(exc),flush=True)
