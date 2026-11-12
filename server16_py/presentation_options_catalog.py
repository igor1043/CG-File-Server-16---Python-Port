"""Dynamic, read-only catalogs from the INI and installed presentation packages."""
from pathlib import Path
from .competition_catalog import presentation_package,settings_text


def safe_name(value):
    return isinstance(value,str) and bool(value) and value not in ('.','..') and not any(c in value for c in '/\\:\r\n\0')


def packages(game,folder,kind,sections):
    game=Path(game);base=game/folder;names=[]
    path=game/'FSW/settings.ini'
    if path.is_file() and path.stat().st_size<=8*1024*1024:
        section=''
        for line in settings_text(path).splitlines():
            line=line.strip()
            if not line or line.startswith((';','#')):continue
            if line.startswith('[') and line.endswith(']'):section=line[1:-1].strip().casefold();continue
            if section not in sections or '=' not in line:continue
            value=line.split('=',1)[1].strip()
            candidates=[value] if safe_name(value) and presentation_package(game,base,kind,value).is_dir() else [s.strip() for s in value.split(',')]
            names.extend(candidates)
    # Unassigned installed packages remain selectable as they were previously.
    if base.is_dir():names.extend(p.name for p in base.iterdir() if p.is_dir())
    found={}
    for name in names:
        if not safe_name(name):continue
        target=presentation_package(game,base,kind,name)
        if not target.is_dir():continue
        found.setdefault(str(target.resolve()).casefold(),name)
    return tuple(sorted(found.values(),key=str.casefold))


def available(game,folder,kind,name):
    return safe_name(name) and presentation_package(game,Path(game)/folder,kind,name).is_dir()
