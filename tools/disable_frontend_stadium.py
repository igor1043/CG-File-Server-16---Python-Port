"""Restore the recorded original stadium script without stopping FIFA."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from server16_py.frontend_stadium import atomic_write
from server16_py.ini_file import IniFile


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-root',type=Path,required=True)
    args=parser.parse_args();game=args.game_root.resolve()
    record_path=game/'ModCarrerMode/runtime/frontend_stadium_install.json'
    record=json.loads(record_path.read_text())
    stadium=game/'data/fifarna/lua/assets/stadium.lua'
    previous=Path(record['backup'])/'stadium.lua'
    expected=record['files'][str(stadium.relative_to(game))]
    current=hashlib.sha256(stadium.read_bytes()).hexdigest()
    if current!=expected and stadium.read_bytes()!=previous.read_bytes():
        raise RuntimeError('stadium.lua has other edits; refusing to overwrite')
    atomic_write(Path(record['backup'])/'stadium.prototype.lua',stadium.read_bytes())
    atomic_write(stadium,previous.read_bytes())
    enabled=game/'ModCarrerMode/mods/enabled.txt'
    text=enabled.read_text(encoding='utf-8-sig')
    owned={f'frontend_stadium\\frontend_stadium_native_v{version}.dll' for version in range(1,12)}
    atomic_write(enabled,('\r\n'.join(line for line in text.splitlines() if line.strip().casefold() not in owned)+'\r\n').encode())
    IniFile(game/'ModCarrerMode/config/frontend_stadium.ini').write('enabled','0','frontend_stadium')
    crowd=game/'data/fifarna/lua/assets/crowd.lua'
    if str(crowd.relative_to(game)) in record['files']:
        if hashlib.sha256(crowd.read_bytes()).hexdigest()!=record['files'][str(crowd.relative_to(game))]:raise RuntimeError('crowd.lua has other edits; refusing to overwrite')
        atomic_write(crowd,(Path(record['backup'])/'crowd.lua').read_bytes())
    for relative,info in record.get('ui',{}).items():
        target=game/relative
        if info['existed']:atomic_write(target,Path(info['backup']).read_bytes())
        else:target.unlink(missing_ok=True)
    record['disabled']=True
    atomic_write(record_path,json.dumps(record,indent=2).encode())
    print('Frontend stadium disabled; original stadium.lua restored; FIFA was not stopped. Restart FIFA to unload the module.')

if __name__=='__main__':main()
