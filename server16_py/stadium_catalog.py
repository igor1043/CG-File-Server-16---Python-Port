from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
import re
import unicodedata

from .file_tools import STADIUM_ARCHIVE_SUFFIXES, resolve_stadium_preview_path

COUNTRIES = {
    'BRA':'Brasil','ARG':'Argentina','ESP':'Espanha','MEX':'México','POR':'Portugal',
    'ENG':'Inglaterra','GER':'Alemanha','ITA':'Itália','FRA':'França','HOL':'Países Baixos',
    'NED':'Países Baixos','USA':'Estados Unidos','CHI':'Chile','COL':'Colômbia',
    'URU':'Uruguai','PAR':'Paraguai','PER':'Peru','ECU':'Equador','BOL':'Bolívia',
    'VEN':'Venezuela','SCO':'Escócia','WAL':'País de Gales','IRL':'Irlanda',
    'NIR':'Irlanda do Norte','BEL':'Bélgica','SWI':'Suíça','SUI':'Suíça',
    'AUT':'Áustria','TUR':'Turquia','GRE':'Grécia','POL':'Polônia','CZE':'Tchéquia',
    'CRO':'Croácia','SRB':'Sérvia','ROM':'Romênia','UKR':'Ucrânia','RUS':'Rússia',
    'SWE':'Suécia','NOR':'Noruega','DEN':'Dinamarca','FIN':'Finlândia','ISL':'Islândia',
    'JAP':'Japão','JPN':'Japão','KOR':'Coreia do Sul','CHN':'China','AUS':'Austrália',
    'SAU':'Arábia Saudita','QAT':'Catar','UAE':'Emirados Árabes Unidos','IND':'Índia',
    'RSA':'África do Sul','EGY':'Egito','MAR':'Marrocos','ALG':'Argélia','ALB':'Albânia',
    'ANG':'Angola','NGA':'Nigéria','SEN':'Senegal','GHA':'Gana','TUN':'Tunísia',
    'CAN':'Canadá','CRC':'Costa Rica','HON':'Honduras','PAN':'Panamá','JAM':'Jamaica',
    'NZL':'Nova Zelândia','IDN':'Indonésia','THA':'Tailândia','IRN':'Irã',
    'FIFA':'Internacional','XXX':'Outros',
    'AZE':'Azerbaijão','BIH':'Bósnia e Herzegovina','BUL':'Bulgária',
    'CIV':'Costa do Marfim','CMR':'Camarões','CPV':'Cabo Verde','CUB':'Cuba',
    'CUW':'Curaçao','CYP':'Chipre','GUA':'Guatemala','HAI':'Haiti','HUN':'Hungria',
    'IRQ':'Iraque','ISR':'Israel','JOR':'Jordânia','KAZ':'Cazaquistão',
    'LIT':'Lituânia','MDA':'Moldávia','MOR':'Marrocos','NEW':'Nova Zelândia',
    'NIC':'Nicarágua','REP':'Irlanda','SER':'Sérvia','SLO':'Eslovênia',
    'SPA':'Espanha','SVK':'Eslováquia','TRI':'Trinidad e Tobago','ZMB':'Zâmbia',
    'BIE':'Bielorrússia','COS':'Costa Rica','GND':'Granada','PTR':'Porto Rico',
    'NIG':'Nigéria','QATAR':'Catar',
}

COUNTRY_FLAGS = {
    'BRA':'br','ARG':'ar','ESP':'es','MEX':'mx','POR':'pt','ENG':'gb-eng',
    'GER':'de','ITA':'it','FRA':'fr','HOL':'nl','NED':'nl','USA':'us',
    'CHI':'cl','COL':'co','URU':'uy','PAR':'py','PER':'pe','ECU':'ec',
    'BOL':'bo','VEN':'ve','SCO':'gb-sct','WAL':'gb-wls','IRL':'ie',
    'NIR':'gb-nir','BEL':'be','SWI':'ch','SUI':'ch','AUT':'at','TUR':'tr',
    'GRE':'gr','POL':'pl','CZE':'cz','CRO':'hr','SRB':'rs','ROM':'ro',
    'UKR':'ua','RUS':'ru','SWE':'se','NOR':'no','DEN':'dk','FIN':'fi',
    'ISL':'is','JAP':'jp','JPN':'jp','KOR':'kr','CHN':'cn','AUS':'au',
    'SAU':'sa','QAT':'qa','UAE':'ae','IND':'in','RSA':'za','EGY':'eg',
    'MAR':'ma','ALG':'dz','ALB':'al','ANG':'ao','NGA':'ng','SEN':'sn',
    'GHA':'gh','TUN':'tn','CAN':'ca','CRC':'cr','HON':'hn','PAN':'pa',
    'JAM':'jm','NZL':'nz','IDN':'id','THA':'th','IRN':'ir',
    'AZE':'az','BIH':'ba','BUL':'bg','CIV':'ci','CMR':'cm','CPV':'cv',
    'CUB':'cu','CUW':'cw','CYP':'cy','GUA':'gt','HAI':'ht','HUN':'hu',
    'IRQ':'iq','ISR':'il','JOR':'jo','KAZ':'kz','LIT':'lt','MDA':'md',
    'MOR':'ma','NEW':'nz','NIC':'ni','REP':'ie','SER':'rs','SLO':'si',
    'SPA':'es','SVK':'sk','TRI':'tt','ZMB':'zm',
    # Legacy package prefixes verified against the installed catalog names.
    'BIE':'by','COS':'cr','GND':'gd','PTR':'pr','NIG':'ng','QATAR':'qa',
}

def normalize(value: str) -> str:
    text = unicodedata.normalize('NFKD', value).casefold()
    return ' '.join(re.sub(r'[^\w]+', ' ', ''.join(c for c in text if not unicodedata.combining(c))).split())

def prematch_page(page: str) -> bool:
    page = (page or '').casefold()
    return page == 'game/screens/playnow/kickoffhub' or any(
        token in page for token in ('kitselect', 'kit_select', 'selectkit', 'prematchhub')
    )

@dataclass(frozen=True)
class StadiumEntry:
    name: str
    country: str
    title: str
    club: str
    team_id: str
    source: Path
    preview: Path | None

    @property
    def searchable(self) -> str:
        return normalize(f'{self.name} {COUNTRIES.get(self.country, self.country)} {self.club}')

def build_catalog(root: Path, settings_ini, teams: dict[str, str]) -> list[StadiumEntry]:
    if not root.is_dir():
        return []
    owners: dict[str, list[str]] = {}
    normalized_teams = [(tid,normalize(club)) for tid,club in teams.items()]
    if settings_ini is not None:
        for team_id, value in settings_ini.items('stadium'):
            if str(team_id) not in teams:
                continue
            for name in value.split(',')[:-3]:
                owners.setdefault(normalize(Path(name.strip()).stem if Path(name.strip()).suffix.lower() in STADIUM_ARCHIVE_SUFFIXES else name.strip()), []).append(str(team_id))
    indexed: dict[str, Path] = {}
    for source in sorted(root.iterdir(), key=lambda p:p.name.casefold()):
        if source.name.startswith('.') or source.name.casefold() == 'render':
            continue
        if source.is_dir() and not any((source/x).is_file() for x in ('model.rx3','texture_day.rx3','texture_night.rx3')):
            continue
        if source.is_file() and source.suffix.lower() not in STADIUM_ARCHIVE_SUFFIXES:
            continue
        name = source.name if source.is_dir() else source.stem
        key = normalize(name)
        if key not in indexed or source.is_dir():
            indexed[key] = source
    result = []
    for key, source in indexed.items():
        name = source.name if source.is_dir() else source.stem
        parts = re.split(r'\s+-\s+', name)
        country = parts[0].upper() if len(parts)>1 and len(parts[0]) in (3,4) else 'XXX'
        title = ' - '.join(parts[1:]) if country != 'XXX' else name
        prefix=re.match(r'^([A-Za-z]{3,5})\s*-\s*(.+)$',name)
        if prefix and (len(prefix[1])==3 or prefix[1].upper() in COUNTRIES):
            country=prefix[1].upper()
            title=prefix[2].strip()
            parts=[country]+re.split(r'\s+-\s+',title)
        tail = normalize(parts[-1]) if len(parts)>2 else ''
        ids = list(dict.fromkeys(owners.get(key, [])))
        # Prefer an explicit club suffix within assigned owners, otherwise use
        # a unique database-name match. Never fabricate a club ID from a name.
        matches = [tid for tid, club in normalized_teams if tail and (
            club==tail or (len(tail)>=5 and f' {tail} ' in f' {club} ')
        )]
        assigned_matches = [tid for tid in ids if tid in matches]
        possible = assigned_matches or matches or ids
        team_id = possible[0] if len(possible)==1 else ''
        club = teams.get(team_id, '')
        result.append(StadiumEntry(name,country,title,club,team_id,source,resolve_stadium_preview_path(root,name)))
    return sorted(result,key=lambda e:(COUNTRIES.get(e.country,e.country),normalize(e.title)))

def filter_catalog(entries: list[StadiumEntry], query: str = '', country: str = '') -> list[StadiumEntry]:
    words = normalize(query).split()
    def matches(entry):
        if country and entry.country!=country:
            return False
        text = entry.searchable
        tokens = text.split()
        return all(word in text or (len(word)>=4 and any(
            SequenceMatcher(None,word,token).ratio()>=0.72 for token in tokens
        )) for word in words)
    result=[entry for entry in entries if matches(entry)]
    if words:
        def score(entry):
            text=entry.searchable
            tokens=text.split()
            return sum(1.0 if word in text else max((SequenceMatcher(None,word,token).ratio() for token in tokens),default=0) for word in words)
        result.sort(key=score,reverse=True)
    return result
