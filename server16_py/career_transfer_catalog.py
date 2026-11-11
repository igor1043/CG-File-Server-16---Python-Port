"""Choose real domestic clubs without altering the underlying career database."""
import re
import unicodedata


_COUNTRY_NAMES = {
    'Brazil':'Brasil','Germany':'Alemanha','England':'Inglaterra','Spain':'Espanha',
    'France':'França','Italy':'Itália','Austria':'Áustria','Belgium':'Bélgica',
    'Croatia':'Croácia','Czech Republic':'Chéquia','Czechia':'Chéquia',
    'Denmark':'Dinamarca','Holland':'Países Baixos','Netherlands':'Países Baixos',
    'Norway':'Noruega','Poland':'Polônia','Romania':'Romênia','Scotland':'Escócia',
    'Sweden':'Suécia','Switzerland':'Suíça','Turkey':'Turquia','Türkiye':'Turquia',
    'Republic of Ireland':'Irlanda','Ireland':'Irlanda','Greece':'Grécia',
    'Ukraine':'Ucrânia','Bolivia':'Bolívia','Colombia':'Colômbia','Ecuador':'Equador',
    'Paraguay':'Paraguai','Uruguay':'Uruguai','Mexico':'México','United States':'Estados Unidos',
    'United States of America':'Estados Unidos','USA':'Estados Unidos',
    'Egypt':'Egito','Morocco':'Marrocos','South Africa':'África do Sul',
    'China PR':'China','Japan':'Japão','Korea Republic':'Coreia do Sul',
    'South Korea':'Coreia do Sul','Saudi Arabia':'Arábia Saudita',
    'United Arab Emirates':'Emirados Árabes Unidos','Australia':'Austrália',
    'Qatar':'Catar','Cameroon':'Camarões','Nigeria':'Nigéria','Russia':'Rússia',
    'Serbia':'Sérvia','Wales':'País de Gales','Algeria':'Argélia','Tunisia':'Tunísia',
    'Finland':'Finlândia','Slovenia':'Eslovênia','Slovakia':'Eslováquia',
    'Bulgaria':'Bulgária','Belarus':'Bielorrússia','Iran':'Irã',
    'Bosnia and Herzegovina':'Bósnia e Herzegovina','Canada':'Canadá','Hungary':'Hungria',
    'Iceland':'Islândia','New Zealand':'Nova Zelândia','Trinidad and Tobago':'Trindade e Tobago',
    "Côte d'Ivoire":'Costa do Marfim','Ivory Coast':'Costa do Marfim','Congo DR':'RD Congo',
    'Zimbabwe':'Zimbábue','Thailand':'Tailândia','Cape Verde':'Cabo Verde',
}


def _words(name):
    text=unicodedata.normalize('NFKD',str(name)).casefold()
    text=''.join(c for c in text if not unicodedata.combining(c))
    return re.findall(r'[a-z0-9]+',text)


_LOCAL_COUNTRIES = {' '.join(_words(name)):label for name,label in _COUNTRY_NAMES.items()}


def country_name(name):
    """Translate labels only; never change nation IDs or the game's database."""
    text=str(name or '').strip()
    return _LOCAL_COUNTRIES.get(' '.join(_words(text)),text)


def _country_names(*sources):
    names={}
    for source in sources:
        rows=source.get('nations',{})
        if isinstance(rows,dict):rows=({'id':ident,'name':name} for ident,name in rows.items())
        for row in rows:
            try:ident=int(row['id'])
            except (KeyError,TypeError,ValueError):continue
            name=str(row.get('name','')).strip()
            if name:names[ident]=name
    return names


def _domestic_country(ident,names):
    # 255 has no valid country binding; 0 is the generic/placeholder group.
    # Regional federations are patch grouping entries, not career destinations.
    if ident in (0,255) or ident not in names:return False
    words=_words(names[ident]);name=' '.join(words)
    return (bool(words) and not name.isdecimal()
            and not (words[0] in ('brasil','brazil') and len(words)>1)
            and name not in ('international','internacional','rest of world','resto do mundo',
                             'free agents','free agents country','agentes livres','selecoes'))


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
    countries=_country_names(reference,data)
    non_club_groups={r['id'] for source in (data,reference) for r in source['leagues']
                     if _non_club_league(r)}
    non_clubs={team for source in (data,reference) for league,team in source['links']
               if league in non_club_groups}
    leagues={r['id']:r for r in data['leagues']
             if r['level']>0 and r['id'] not in non_club_groups and not _access_league(r)
             and _domestic_country(r['country_id'],countries)}
    links=[(league,team) for league,team in data['links'] if league in leagues and team not in non_clubs]
    active={league for league,team in links}
    teams={team for league,team in links}
    active_countries={leagues[ident]['country_id'] for ident in active}
    return dict(data,nations={str(ident):country_name(countries[ident]) for ident in sorted(active_countries)},
                leagues=[r for r in data['leagues'] if r['id'] in active],
                teams=[r for r in data['teams'] if r['id'] in teams],links=links)
