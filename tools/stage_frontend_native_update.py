"""Install a new native DLL for the next launch without touching the running game."""
import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from server16_py.frontend_stadium import atomic_write


def stage(game,dll):
    game=Path(game).resolve();dll=Path(dll).resolve()
    record=game/'ModCarrerMode/runtime/frontend_stadium_install.json'
    old=json.loads(record.read_text(encoding='utf8'))
    version=11
    if old.get('version') not in (6,7,8,9,10):raise ValueError('This update requires the installed version 6/7/8/9/10 UI/helper/server')
    # Refuse an unknown or partially modified installation before changing it.
    for name,digest in old['files'].items():
        if hashlib.sha256((game/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('Installed file changed: '+name)
    raw=dll.read_bytes()
    if raw[:2]!=b'MZ':raise ValueError('Invalid native DLL')
    destination=game/f'ModCarrerMode/mods/frontend_stadium/frontend_stadium_native_v{version}.dll'
    if destination.exists():raise FileExistsError('Refusing to replace a possibly loaded DLL: '+str(destination))
    enabled=game/'ModCarrerMode/mods/enabled.txt'
    before=enabled.read_bytes()
    backup=game/'ModCarrerMode/backups'/(f'frontend_native_v{version}_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
    backup.mkdir(parents=True,exist_ok=False)
    (backup/'enabled.txt').write_bytes(before)
    (backup/'frontend_stadium_install.json').write_bytes(record.read_bytes())
    # Copy under a fresh name. The currently loaded image and running process
    # remain untouched; the host reads enabled.txt again at the next launch.
    atomic_write(destination,raw)
    owned={f'frontend_stadium\\frontend_stadium_native_v{v}.dll' for v in range(1,version+1)}
    lines=[line for line in before.decode('utf-8-sig').splitlines() if line.strip().casefold() not in owned]
    lines.append(f'frontend_stadium\\frontend_stadium_native_v{version}.dll')
    atomic_write(enabled,('\r\n'.join(lines)+'\r\n').encode('utf8'))
    report=dict(old)
    report.update(version=version,requires_restart=True,native_update_backup=str(backup),
                  activation='Next FIFA launch; running game is unchanged')
    report['files']={name:digest for name,digest in old['files'].items() if 'frontend_stadium_native_v' not in name}
    report['files'][str(destination.relative_to(game))]=hashlib.sha256(raw).hexdigest()
    atomic_write(record,json.dumps(report,indent=2).encode('utf8'))
    source=game/'ModCarrerMode/source/frontend_stadium'
    source.mkdir(parents=True,exist_ok=True)
    for path in (ROOT/'native_mods/frontend_stadium').iterdir():
        if path.is_file():shutil.copy2(path,source/path.name)
    print(json.dumps(report,indent=2))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-root',type=Path,required=True)
    parser.add_argument('--dll',type=Path,required=True)
    args=parser.parse_args();stage(args.game_root,args.dll)
