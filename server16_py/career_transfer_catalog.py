"""Choose real domestic clubs without altering the underlying career database."""
import re
import unicodedata


def _words(name):
    text=unicodedata.normalize('NFKD',str(name)).casefold()
    text=''.join(c for c in text if not unicodedata.combining(c))
    return re.findall(r'[a-z0-9]+',text)


def _non_club_league(league):
    # These native group IDs are confirmed by the installed league database.
    # Match whole group names too, without excluding England's National League.
    return (league['id'] in (78,382) or ' '.join(_words(league['name'])) in (
        'international','internationals','national teams','selecoes','selecoes nacionais',
        'selecoes internacionais','free agents','free agents league','agentes livres',
        'women s international','womens international','women s national teams'))


def _access_league(league):
    words=_words(league['name'])
    return ('acesso' in words or 'acceso' in words
            or ('access' in words and any(w in words for w in ('division','league'))))


def transfer_catalog(data, reference=None):
    """Filter the current career's links; base membership only identifies national/FA teams.

    Access clubs are not globally blacklisted: a promotion into a normal division
    in the save must make that club selectable in its new division.
    """
    reference=reference or data
    non_club_groups={r['id'] for source in (data,reference) for r in source['leagues']
                     if _non_club_league(r)}
    non_clubs={team for source in (data,reference) for league,team in source['links']
               if league in non_club_groups}
    leagues={r['id']:r for r in data['leagues']
             if r['level']>0 and r['id'] not in non_club_groups and not _access_league(r)}
    links=[(league,team) for league,team in data['links'] if league in leagues and team not in non_clubs]
    active={league for league,team in links}
    teams={team for league,team in links}
    return dict(data,leagues=[r for r in data['leagues'] if r['id'] in active],
                teams=[r for r in data['teams'] if r['id'] in teams],links=links)
