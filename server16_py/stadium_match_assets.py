"""Keep each match stadium model and its textures under one immutable identity."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path


def stage_match_assets(transaction, slot: str, home: str, away: str) -> tuple[str, Path]:
    folder = transaction.stage/'data/sceneassets/stadium'
    sources = {
        'model': folder/f'stadium_{slot}.rx3',
        'day': folder/f'stadium_{slot}_1_textures.rx3',
        'night': folder/f'stadium_{slot}_3_textures.rx3',
    }
    fingerprints = {}
    for name, path in sources.items():
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f'Stadium {slot} has no complete {name} resource')
        with path.open('rb') as stream:
            fingerprints[name] = hashlib.file_digest(stream, 'sha256').hexdigest()
    identity = hashlib.sha256(json.dumps(fingerprints, sort_keys=True).encode()).hexdigest()[:32]
    parent = Path('data/sceneassets/server16_match')/identity
    paths = {}
    for name, source in sources.items():
        relative = parent/(name+'.rx3')
        existing = transaction.game/relative
        reuse = False
        if existing.is_file() and existing.stat().st_size == source.stat().st_size:
            with existing.open('rb') as stream:
                reuse = hashlib.file_digest(stream, 'sha256').hexdigest() == fingerprints[name]
        if not reuse:
            if existing.exists():
                raise RuntimeError(f'Stadium cache was modified: {relative}')
            target = transaction.stage/relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        paths[name] = relative.as_posix()
    # The route is part of the same rollback transaction and becomes available
    # before FIFA's stadium ID changes. Home/away guards reject an old fixture.
    home, away = int(str(home).split()[0]), int(str(away).split()[0])
    route = Path(f'data/fifarna/lua/assets/server16_match_{slot}.lua')
    body = 'Server16MatchRoutes = Server16MatchRoutes or {}\n'
    body += f'Server16MatchRoutes[{int(slot)}] = {{ home = {home}, away = {away}, '
    body += ', '.join(f'{name} = {json.dumps(path)}' for name,path in paths.items())+' }\n'
    target = transaction.stage/route
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding='ascii')
    return identity, route


def clear_match_routes(game: Path) -> None:
    # Leave immutable assets alive: the engine can still be releasing them.
    for slot in (176, 261):
        target = Path(game)/f'data/fifarna/lua/assets/server16_match_{slot}.lua'
        if not target.exists():
            continue
        temporary = target.with_suffix('.lua.tmp')
        temporary.write_text(f'Server16MatchRoutes = Server16MatchRoutes or {{}}\nServer16MatchRoutes[{slot}] = nil\n', encoding='ascii')
        temporary.replace(target)
