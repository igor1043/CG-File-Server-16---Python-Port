"""Resolve installed object numbers through the competition's semantic identity."""
import csv
from functools import lru_cache
from pathlib import Path
import re

COMP_OBJ = Path('dlc/dlc_FootballCompEng/dlc/FootballCompEng/data/compdata/compobj.txt')
ICON_MAP = Path('ModCarrerMode/data/catalogs/career_competition_icon_map.tsv')
PRESENTATION_ALIASES = Path('ModCarrerMode/data/catalogs/presentation_package_aliases.tsv')


def settings_text(path):
    data = Path(path).read_bytes()
    try:
        return data.decode('utf-8-sig')
    except UnicodeDecodeError:
        return data.decode('cp1252')


def presentation_package(game, base, kind, requested):
    """Keep author-provided settings names while locating an existing package."""
    direct = Path(base) / requested
    if direct.is_dir():
        return direct
    path = Path(game) / PRESENTATION_ALIASES
    if not path.is_file():
        return direct
    candidates = set()
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        parts = line.split('|')
        if len(parts) != 3 or parts[:2] != [kind, requested]:
            continue
        source = parts[2]
        if source and source not in ('.', '..') and not any(c in source for c in '/\\:'):
            candidates.add(source)
    if len(candidates) == 1:
        alias = Path(base) / candidates.pop()
        if alias.is_dir():
            return alias
    return direct


@lru_cache(maxsize=12)
def _nodes(path, stamp, size):
    result = {}
    for row in csv.reader(Path(path).read_text(encoding='utf-8-sig').splitlines()):
        if len(row) >= 5 and row[0].isdigit() and row[1].isdigit():
            ident = int(row[0])
            if not 0 <= ident <= 65535 or ident in result:
                raise ValueError('CompData com ID inválido ou repetido')
            result[ident] = (int(row[1]), row[2], row[3], int(row[4]))
    return result


def nodes(game):
    path = Path(game) / COMP_OBJ
    if not path.is_file():
        return {}
    stat = path.stat()
    return _nodes(str(path), stat.st_mtime_ns, stat.st_size)


def identity_key(objects, ident):
    chain = []
    for _ in range(64):
        row = objects.get(int(ident))
        if row is None or any(c in row[1] + row[2] for c in '|~:'):
            return None
        if any(other != int(ident) and candidate[:3] == row[:3]
               and (row[0] == 3 or candidate[3] == row[3]) for other, candidate in objects.items()):
            return None
        chain.append(f'{row[0]}:{row[1]}:{row[2]}')
        if row[0] == 3:
            return '~'.join(reversed(chain))
        ident = row[3]
    return None


def visual(row):
    match = re.search(r'TrophyName_Abbr15_(\d+)', row[2]) or re.fullmatch(r'C(\d+)', row[1])
    return int(match[1]) if match and 0 < int(match[1]) <= 65535 else 0


def icon_mapping(game):
    objects = nodes(game)
    mapping = {ident: visual(row) for ident, row in objects.items() if row[0] == 3 and visual(row)}
    path = Path(game) / ICON_MAP
    if path.is_file():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            fields = line.split('|')
            if len(fields) not in (2, 4) or not all(value.strip().isdigit() for value in fields[:2]):
                continue
            hint, asset = map(int, fields[:2])
            if not 0 < asset <= 65535:
                continue
            if len(fields) == 4:
                matches = [ident for ident, row in objects.items()
                           if row[0] == 3 and (row[1], row[2]) == tuple(fields[2:])]
                if len(matches) == 1:
                    mapping[matches[0]] = asset
            elif hint in mapping and mapping[hint] == asset:
                mapping[hint] = asset
    return mapping
