"""Prepare isolated 3D assets for favorite-team and career menu panoramas.

The native bridge requests a team before FIFA loads its front-end scene. Match
injection files and databases are never changed by this module.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import struct
import tempfile
import time
import unicodedata
from pathlib import Path

from .file_tools import extract_archive
from .ini_file import SessionIniFile

SLOTS = (176, 261)
LUA_MARKER = '-- Server16 frontend stadium v1'


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name+'.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def transparent_dds() -> bytes:
    # One valid 4x4 DXT5 block: alpha endpoints and all alpha indices are zero.
    header = [124, 0x81007, 4, 4, 16, 0, 0] + [0]*11
    header += [32, 4, int.from_bytes(b'DXT5', 'little'), 0, 0, 0, 0, 0]
    header += [0x1000, 0, 0, 0, 0]
    return b'DDS ' + struct.pack('<31I', *header) + bytes(16)


def assignment_names(value: str) -> list[str]:
    parts = [part.strip() for part in value.split(',') if part.strip()]
    return [name.strip() for name in parts[:-3]
            if name.strip() and name.strip().casefold() != 'none']


def resolve_source(library: Path, name: str) -> Path:
    if Path(name).is_absolute() or '/' in name or '\\' in name or name in ('.', '..'):
        raise ValueError('Stadium name must be a single library entry')
    fold = lambda text: unicodedata.normalize('NFC', text).casefold()
    wanted = fold(name)
    for suffix in ('', '.zip', '.rar'):
        source = library / (name+suffix)
        if source.is_dir() or source.is_file() and source.suffix.casefold() in ('.rar', '.zip'):
            return source
    for source in library.iterdir():
        if source.is_dir() and fold(source.name) == wanted:
            return source
        if source.suffix.casefold() in ('.zip', '.rar') and fold(source.stem) == wanted:
            return source
    raise FileNotFoundError(f'Stadium package not found: {name}')


def package_root(folder: Path) -> Path:
    candidates = [path.parent for path in folder.rglob('model.rx3') if path.is_file()]
    if (folder/'model.rx3').is_file():
        candidates.append(folder)
    candidates = sorted(set(candidates), key=lambda p: (len(p.relative_to(folder).parts), str(p)))
    if len(candidates) != 1:
        raise ValueError(f'Expected exactly one model.rx3, found {len(candidates)}')
    return candidates[0]


def validate_package(folder: Path) -> None:
    # A model without its matching texture set must never uncover the photograph.
    for filename in ('model.rx3', 'texture_day.rx3'):
        path = folder/filename
        if not path.is_file() or path.is_symlink() or path.stat().st_size < 32:
            raise ValueError(f'Invalid stadium resource: {filename}')
        with path.open('rb') as handle:
            magic = handle.read(3)
        if magic != b'RX3':
            raise ValueError(f'Not an RX3 resource: {filename}')


def display_name(settings, name):
    configured=settings.read(name,'scoreboardstdname').rsplit(',',1)[0].strip()
    return configured or name


def publish_metadata(game, result):
    # Win32's INI reader accepts UTF-16, including stadium names with accents.
    lines=['[frontend_stadium]',f"mode={result.get('mode',1)}",f"team={result['team']}",
           f"slot={result['slot']}",f"name={result.get('display_name','')}",
           f"crowd={result.get('crowd','')}",
           f"capacity={result.get('capacity') if result.get('capacity') is not None else ''}",
           f"attendance={result.get('attendance') if result.get('attendance') is not None else ''}"]
    atomic_write(game/'ModCarrerMode/runtime/frontend_stadium_route.ini', ('\r\n'.join(lines)+'\r\n').encode('utf-16'))
    if result.get('mode',1)!=1:
        for slot in SLOTS:
            atomic_write(game/f'data/fifarna/lua/assets/server16_frontend_{slot}.lua',
                         f'Server16FrontendRoutes = Server16FrontendRoutes or {{}}\nServer16FrontendRoutes[{slot}] = nil\n'.encode())


def native_fallback(game,team,slot):
    catalog=game/'ModCarrerMode/data/catalogs/club_stadium_fallback.tsv'
    if catalog.is_file():
        for line in catalog.read_text(encoding='utf-8-sig').splitlines():
            row=line.split('|')
            # The custom-name column is a historical catalogue hint, not an
            # installed assignment. Keep the club's native ground unless FSW
            # or the current user's selection explicitly chooses a package.
            if len(row)>=5 and row[0]==str(team) and row[1].isdigit() and int(row[1])>0:
                return {'mode':2,'team':team,'slot':int(row[1]),'display_name':row[3],'source':'native_catalog'}
    return {'mode':0,'team':team,'slot':slot,'display_name':'','source':'unassigned'}


def prepare(game: Path, team: int, slot: int, *, publish=True, library=None, career=False, session=0) -> dict:
    started = time.monotonic()
    game = Path(game).resolve()
    if not 0 < team <= 2_000_000 or slot not in SLOTS:
        raise ValueError('Invalid team or front-end slot')
    settings = SessionIniFile(game/'FSW/settings.ini')
    names = assignment_names(settings.read(str(team), 'stadium'))
    from .frontend_stadium_selection import selection
    override=selection(game,team,career=career,session=session)
    if override and override.casefold()!='auto':names=[override]
    if not names:
        raise LookupError(f'No custom stadium assigned to team {team}')
    library = Path(library) if library else game/'StadiumGBD'
    # Deterministic first installed entry; menu visits must not reroll a club's stadium.
    errors = []
    for name in names:
        try:
            source = resolve_source(library, name)
            break
        except FileNotFoundError as error:
            errors.append(str(error))
    else:
        raise FileNotFoundError('; '.join(errors))
    if source.is_dir():
        original = package_root(source)
        stamps = [(str(p.relative_to(original)), p.stat().st_size, p.stat().st_mtime_ns)
                  for p in sorted(original.rglob('*')) if p.is_file()]
    else:
        stat = source.stat()
        stamps = [(source.name, stat.st_size, stat.st_mtime_ns)]
    key = hashlib.sha256(json.dumps(['frontend-v3', str(source.resolve()), stamps], ensure_ascii=False).encode()).hexdigest()[:24]
    relative = Path('data/sceneassets/server16_frontend') / key
    cache = game/relative
    record_path = cache/'ready.json'
    cache_hit = record_path.is_file()
    extractor = 'cache' if cache_hit else 'folder'
    if not cache_hit:
        cache.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.preparing_', dir=cache.parent) as temporary:
            stage = Path(temporary)
            if source.is_dir():
                original = package_root(source)
            else:
                extractor = extract_archive(source, stage/'extracted')
                original = package_root(stage/'extracted')
            validate_package(original)
            prepared = stage/'ready'
            prepared.mkdir()
            for src in original.rglob('*'):
                if src.is_file() and not src.is_symlink():
                    dest=prepared/src.relative_to(original)
                    dest.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copy2(src,dest)
            record = {'version':3, 'key':key, 'source':str(source), 'name':name}
            (prepared/'ready.json').write_text(json.dumps(record, ensure_ascii=False), encoding='utf8')
            if not cache.exists():
                os.replace(prepared, cache)
    validate_package(cache)
    result = {'mode':1,'team':team, 'slot':slot, 'name':name, 'key':key,'display_name':display_name(settings,name),
              'source':str(source), 'archive':source.is_file(), 'cache_hit':cache_hit,
              'extractor':extractor, 'elapsed_ms':round((time.monotonic()-started)*1000),
              'model':(relative/'model.rx3').as_posix(),
              'day':(relative/'texture_day.rx3').as_posix(),
              'night':(relative/('texture_night.rx3' if (cache/'texture_night.rx3').is_file() else 'texture_day.rx3')).as_posix()}
    result['crowd']=(relative/'crowd_day.dat').as_posix() if (cache/'crowd_day.dat').is_file() else ''
    result['chairs']=(relative/'NoSeats.rx3').as_posix() if (cache/'NoSeats.rx3').is_file() else ('' if result['crowd'] else 'data/sceneassets/crowdchair/crowdchair_empty.rx3')
    from .stadium_metadata import read_custom_metadata
    result.update(read_custom_metadata(game,name,cache))
    if publish:
        # The native BackgroundDP hook selects this NEW transparent resource
        # only while the custom FE scene is active. Original photos stay intact.
        photo = game/'data/ui/imgAssets/backgroundstadiums/st_server16_frontend_clear.dds'
        body = LUA_MARKER+'\nServer16FrontendRoutes = Server16FrontendRoutes or {}\n'
        body += f'Server16FrontendRoutes[{slot}] = {{ team = {team}, '
        body += ', '.join(f'{key} = {json.dumps(result[key])}' for key in ('model','day','night','crowd','chairs')) + ' }\n'
        atomic_write(game/f'data/fifarna/lua/assets/server16_frontend_{slot}.lua', body.encode('ascii'))
        atomic_write(photo, transparent_dds())
        publish_metadata(game,result)
        atomic_write(game/'ModCarrerMode/runtime/frontend_stadium_last.json', json.dumps(result, ensure_ascii=False, indent=2).encode('utf8'))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-root', type=Path, required=True)
    parser.add_argument('--team', type=int, required=True)
    parser.add_argument('--slot', type=int, choices=SLOTS, required=True)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--library', type=Path)
    parser.add_argument('--career', action='store_true')
    parser.add_argument('--session', type=int, default=0)
    args = parser.parse_args(argv)
    try:
        result = prepare(args.game_root, args.team, args.slot, publish=not args.prepare_only, library=args.library,
                         career=args.career,session=args.session)
        print(json.dumps(result, ensure_ascii=True))
        return 0
    except LookupError:
        result=native_fallback(args.game_root,args.team,args.slot)
        if not args.prepare_only:publish_metadata(args.game_root,result)
        print(json.dumps(result));return 0
    except Exception as error:
        if not args.prepare_only:
            publish_metadata(args.game_root,{'mode':0,'team':args.team,'slot':args.slot})
        log = args.game_root/'ModCarrerMode/logs/frontend_stadium_prepare.log'
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open('a', encoding='utf8') as handle:
            handle.write(f'team={args.team} slot={args.slot}: {type(error).__name__}: {error}\n')
        print(str(error));return 1
