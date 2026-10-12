"""Package built files only. Never changes any game installation."""
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'dist' / 'MatchPresentation'
FILES = (
    ('mod', 'ModCarrerMode/mods/mascot_single/mascot_goal_line_v26.dll', 'build/mascot_goal_line_v26.dll',
     '66435B2FF01679EB16ECA91F61CA2F93391AF95FA8BE4FCDEEA99E91C0C1C405'),
    ('mod', 'ModCarrerMode/mods/stadium_pyrotechnics/stadium_pyrotechnics.dll', 'build/stadium_pyrotechnics.dll',
     'A8954AC4B57B778EA1D99F287F1CDAACEE0A231F6D9CC76FE23583C68AB530B2'),
    ('server', 'Server16Python.exe', 'dist/Server16Python.exe', ''),
)


def main():
    entries = []
    for kind, relative, source, original in FILES:
        src, dst = ROOT/source, DEST/relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        entries.append(dict(kind=kind, relative=relative, original_sha256=original,
                            sha256=hashlib.sha256(dst.read_bytes()).hexdigest().upper()))
    for name in ('README.md', 'Install-MatchPresentation.ps1'):
        shutil.copy2(ROOT/'native_mods'/name, DEST/name)
    (DEST/'manifest.json').write_text(json.dumps(dict(files=entries), indent=2)+'\n', encoding='utf-8')
    print(DEST)


if __name__ == '__main__':
    main()
