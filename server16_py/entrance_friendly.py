"""Resolve a friendly's common domestic league using installed database IDs."""
from __future__ import annotations

import csv
import re
from pathlib import Path

from .ini_file import SessionIniFile

COMPETITION_SECTIONS = ('movies', 'Scoreboard', 'comp')
COMP_OBJECTS = Path('dlc/dlc_FootballCompEng/dlc/FootballCompEng/data/compdata/compobj.txt')


def identifier(value: str) -> bool:
    return bool(re.fullmatch(r'[1-9][0-9]{0,5}', value or ''))


def no_competition(value: str) -> bool:
    return value in ('', '0')


def common_league_competition(game_root: Path, home: str, away: str, database, settings=None) -> tuple[str, str, str]:
    """Return (competition node, database league, status), never guess by name.

    compobj's competition object C7 connects the database league 7 to node
    1738. Only an exact, unambiguous node already present in settings.ini is
    accepted. This is game data, not a second editable model mapping.
    """
    root = Path(game_root)
    if not identifier(home) or not identifier(away):
        return '', '', 'friendly_teams_invalid'
    if database is None:
        return '', '', 'friendly_database_pending'
    try:
        home_league = str(database.get_team_league_id(home) or '')
        away_league = str(database.get_team_league_id(away) or '')
        if not identifier(home_league) or not identifier(away_league):
            return '', '', 'friendly_league_unknown'
        if home_league != away_league:
            return '', '', 'friendly_different_leagues'
        path = root / COMP_OBJECTS
        if not path.is_file():
            return '', home_league, 'friendly_competition_data_missing'
        settings = settings if settings is not None else SessionIniFile(root/'FSW/settings.ini')
        matches = set()
        with path.open(encoding='utf-8-sig', errors='replace', newline='') as handle:
            for row in csv.reader(handle):
                if len(row) >= 3 and row[1].strip() == '3' and row[2].strip() == 'C'+home_league:
                    node = row[0].strip()
                    if identifier(node) and any(settings.key_exists(node, section) for section in COMPETITION_SECTIONS):
                        matches.add(node)
        if len(matches) != 1:
            return '', home_league, 'friendly_league_unconfigured' if not matches else 'friendly_league_ambiguous'
        return matches.pop(), home_league, 'friendly_same_league'
    except (OSError, AttributeError, TypeError, ValueError, csv.Error):
        return '', '', 'friendly_league_unavailable'
