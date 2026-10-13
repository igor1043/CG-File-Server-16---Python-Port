"""Match club mentions by team identity and compatible commentary scene."""
import collections
import json
import re

from core import connect, WORK
from generic_policy import female_reference, plain


FEMALE_CUES = re.compile(r'\b(?:meninas|mulherada|jogadoras?|atletas|feminina|feminino)\b')
SUFFIXES = re.compile(r'\b(?:fc|cf|sc|afc|ac|ss|ud|cd|rc|se|cr|ec|clube|club|football|futebol)\b')
STOP_ALIAS = {'united', 'city', 'sporting', 'athletic', 'national', 'nacional', 'internacional'}

# Reviewed ASR variants from the extracted Brazilian 00_TEAM banks. These are
# direct identity labels, not fuzzy guesses; keep them tied to a unique FIFA
# team ID so similarly named clubs cannot absorb the call.
REVIEWED_CLUB_LABELS = {
    'bota fogo': '517',
    'corintians': '1041',
    'atletico mineiro': '1035',
    'atletico gonnc': '112119',
    'atletico parada nc': '1039',
    'fiorentina': '110374',
    'cristiuma': '111046',
    'figue a danca': '111045',
    'afaii': '111976',
    'bai': '1598',
    'esporte recife': '111057',
    'somos caetano': '1789',
    'bota fogo de ribeirao preto': '130028',
    'bota fogo de riberao preto': '130028',
}

# These bare labels are shared with lower-division clubs in the game's
# metadata. The PES call is the well-known Brazilian top-flight club.
REVIEWED_BARE_TEAMS = {'fluminense': '567', 'vitoria': '1719'}


def _team_ids(teams, exact=None, includes=()):
    exact = plain(exact or '')
    includes = tuple(plain(value) for value in includes)
    result = []
    for team_id, name in teams.items():
        value = plain(name)
        if (exact and value == exact) or (includes and all(part in value for part in includes)):
            result.append(str(team_id))
    return result


def team_aliases():
    """Load canonical FIFA team IDs and only add reviewed speech variants."""
    path = WORK / 'metadata' / 'game_names.json'
    teams = json.loads(path.read_text(encoding='utf-8-sig')).get('teams', {}) if path.is_file() else {}
    aliases = collections.defaultdict(set)

    def add(alias, ids, allow_short=False):
        value = plain(alias)
        if (len(value) >= 4 or (allow_short and len(value) >= 3)) and ids:
            aliases[value].update(map(str, ids))

    for team_id, name in teams.items():
        full = plain(name)
        add(full, [team_id])
        short = ' '.join(SUFFIXES.sub(' ', full).split())
        if len(short) >= 5 and short not in STOP_ALIAS:
            add(short, [team_id])

    reviewed = (
        (('Manchester City',), ('Man City', 'Mantiacer City', 'Mante Exercite', 'Manche Estercite')),
        (('Paris', 'Germain'), ('PSG', 'Paris Sa Germain', 'Paris Seingerman', 'Paris Sancho Irma',
                                'Paris Sao Germain', 'Paris Sem German', 'Paris Saint Germain')),
        (('Lyon',), ('Leon',)),
        (('Borussia', 'Dortmund'), ('Dortmund',)),
        (('Atletico', 'Madrid'), ('Atletico de Madrid',)),
    )
    for fragments, variants in reviewed:
        ids = _team_ids(teams, includes=fragments)
        if len(ids) == 1:
            for variant in variants:
                add(variant, ids, allow_short=True)
    # Reviewed ASR variants heard repeatedly in the Brazilian club-call bank.
    # These are tied to a unique canonical FIFA team name, never guessed from
    # a generic token such as “City” or “Leão”.
    for canonical, variants in {
        'chelsea': ('TLC', 'Tchau-se', 'Tchau se'),
        'liverpool': ('Liverpo', 'Liberpo', 'Contraliverpo', 'Contro Liverpo'),
        'manchester city': ('Mante Exerciti', 'Mantecer Citi', 'Mae Chester City'),
        'paris saint germain': ('Paris Sem Germã', 'Paris Sa Germain', 'Paris São Germã',
                                'Paris Sã-German', 'Paris San Germain'),
    }.items():
        ids = aliases.get(plain(canonical), set())
        if len(ids) == 1:
            for variant in variants:
                add(variant, ids, allow_short=True)
    for variant, team_id in REVIEWED_CLUB_LABELS.items():
        if team_id in teams:
            add(variant, [team_id], allow_short=True)
    for label, team_id in REVIEWED_BARE_TEAMS.items():
        if team_id in teams:
            aliases[label] = {team_id}
    return aliases


def resolve_team(text, aliases):
    normalized = plain(text or '')
    reviewed_id = REVIEWED_BARE_TEAMS.get(normalized)
    if reviewed_id and reviewed_id in aliases.get(normalized, set()):
        return reviewed_id, normalized, True
    value = ' ' + normalized + ' '
    found = []
    for alias in sorted(aliases, key=lambda item: (-len(item), item)):
        needle = ' ' + alias + ' '
        start = 0
        while True:
            index = value.find(needle, start)
            if index < 0:
                break
            begin = index + 1
            end = begin + len(alias)
            found.extend((team_id, alias, begin, end) for team_id in aliases[alias])
            start = begin + 1
    # Prefer the most specific recognized phrase where aliases overlap (for
    # example, “Paris São Germã” must beat the shorter team alias “Paris”).
    found = [candidate for candidate in found if not any(
        other[2] <= candidate[2] and other[3] >= candidate[3]
        and (other[3] - other[2]) > (candidate[3] - candidate[2])
        for other in found)]
    ids = {team_id for team_id, _, _, _ in found}
    if len(ids) != 1:
        return None, '', False
    team_id = next(iter(ids))
    matched = max((alias for found_id, alias, _, _ in found if found_id == team_id), key=len)
    remainder = value.replace(' ' + matched + ' ', ' ')
    remainder_words = [word for word in remainder.split() if word not in {'e', 'o', 'a', 'os', 'as', 'de', 'do', 'da', 'dos', 'das'}]
    return team_id, matched, not remainder_words


def team_role(event, bare=False, topic=''):
    value = (event or '').upper()
    # PES 00_TEAM banks contain standalone club names but no FIFA event key.
    # They are safe only as bare labels, which compatible_role restricts to
    # the corresponding home/away introduction slots.
    if not value and topic == 'Nomes de clubes':
        return 'team_label'
    if 'TS_TEAM_INTRO_NUM_CHANGES' in value:
        return 'lineup_changes'
    if value == 'TTS_TEAM_INTRO':
        return 'lineup'
    if value == 'TINTRO_STITCH_HOME' or 'INTRO_SEQ1_WRAP_UP_TEAM_A' in value:
        return 'intro_home'
    if value == 'TINTRO_STITCH_AWAY' or 'INTRO_SEQ1_WRAP_UP_TEAM_B' in value:
        return 'intro_away'
    if value in ('TATTACKING_ENTRY', 'TATTACK_ENTRY_GENERIC'):
        return 'attack_entry'
    # Keep event identity for team-specific goals, fouls, substitutions,
    # transfers, scorelines and similar scenes. Only the lineup and generic
    # attack-entry cases above intentionally share recordings across keys.
    if value and (re.search(r'(?:^|_)TEAM(?:_|$)', value)
                  or topic in ('Nomes de clubes', 'Comentários de clubes')
                  or any(token in value for token in ('CORNER', 'FOUL', 'SUB', 'FULLTIME',
                                                       'HALFTIME', 'THROW', 'POSSESSION', 'TCKL'))):
        return 'event:' + value
    return ''


def compatible_role(target, source, source_bare):
    if target == source:
        return True
    if target == 'lineup_changes' and source == 'lineup':
        # A plain lineup call stays accurate when the target names changes;
        # the reverse would invent a change count for a plain lineup scene.
        return True
    if target in ('intro_home', 'intro_away') and source_bare:
        return True
    if target == 'team_label' and source in ('intro_home', 'intro_away') and source_bare:
        return True
    if target == 'opponent_label' and source == 'intro_away':
        return True
    return False


def female_line(text, bank=''):
    return 'female' in (bank or '').casefold() or female_reference(text or '') or bool(FEMALE_CUES.search(plain(text or '')))


def run(name, db=None, write_report=True):
    owns_db = db is None
    if owns_db:
        db = connect()
    aliases = team_aliases()
    sources = collections.defaultdict(list)
    for row in db.execute("SELECT * FROM sources WHERE narrator=? AND transcript!='' AND error=''", (name,)):
        role = team_role(row['event'], topic=row['topic'])
        if not role:
            continue
        team_id, _, bare = resolve_team(row['transcript'], aliases)
        if not team_id:
            continue
        if row['confidence'] is not None and row['confidence'] < -1.0:
            continue
        source = dict(row)
        source['team_id'] = team_id
        source['role'] = role
        source['bare'] = bare
        source['female'] = female_line(source['transcript'], source['path'])
        sources[(team_id, role)].append(source)

    preserved = {row['clip'] for row in db.execute(
        "SELECT clip FROM mappings WHERE profile=? AND method IN ('manual','boundary_cleanup','gender_review')", (name,))}
    seen = set()
    used = collections.Counter()
    updates = []
    report = []
    with db:
        db.execute("DELETE FROM mappings WHERE profile=? AND method IN ('club_transcript_exact','club_entity_context')", (name,))
        for row in db.execute('''SELECT c.*,b.name AS bank_name FROM clips c JOIN banks b ON c.bank=b.key
                WHERE b.active=1 ORDER BY c.bank,c.offset'''):
            identity = (row['bank'], row['offset'])
            if identity in seen:
                continue
            seen.add(identity)
            role = team_role(row['event'], topic=row['topic'])
            if not role:
                continue
            team_id, _, _ = resolve_team(row['transcript'], aliases)
            if not team_id:
                continue
            target_female = female_line(row['transcript'], row['bank_name'])
            pool = []
            for (source_team, source_role), candidates in sources.items():
                if source_team != team_id:
                    continue
                pool.extend(source for source in candidates
                            if compatible_role(role, source_role, source['bare'])
                            and (not source['female'] or target_female))
            alias_rows = db.execute('SELECT key FROM clips WHERE bank=? AND offset=?', identity).fetchall()
            if not pool or any(alias['key'] in preserved for alias in alias_rows):
                continue
            pool.sort(key=lambda source: (
                source['role'] != role,
                source['female'] != target_female,
                used[source['key']],
                -(source['confidence'] if source['confidence'] is not None else -2.0),
                source['path'],
            ))
            source = pool[0]
            used[source['key']] += 1
            updates.extend((name, alias['key'], source['key'], 'club_entity_context', 0.98) for alias in alias_rows)
            report.append(dict(event=row['event'], team_id=team_id, original=row['transcript'],
                               replacement=source['transcript'], source_event=source['event'],
                               source=source['path'], target_female=target_female, source_female=source['female']))
        db.executemany('INSERT OR REPLACE INTO mappings VALUES (?,?,?,?,?)', updates)
    if owns_db:
        db.close()
    if write_report:
        destination = WORK / 'transcriptions'
        destination.mkdir(exist_ok=True)
        (destination / (name + '_club_associations.json')).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    summary = dict(narrator=name, physical_occurrences=len(report), occurrences=len(updates),
                   unique_sources=len(used), teams=len({row['team_id'] for row in report}),
                   event_counts=dict(collections.Counter(row['event'] for row in report)))
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return summary


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('narrator')
    run(parser.parse_args().narrator)
