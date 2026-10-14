"""Competition identities from Server configuration; names never replace IDs."""
from pathlib import Path
import configparser,json,random,re
from .narration_paths import narration_root

def competitions(game):
    ini=configparser.ConfigParser(interpolation=None,strict=False);ini.optionxform=str
    path=Path(game)/'FSW/settings.ini'
    if path.exists():
        # Old Server INIs can contain malformed unrelated sections. Only
        # the configured competition IDs are relevant to this picker.
        text=path.read_text(encoding='utf-8-sig',errors='replace')
        for section in ('comp','Scoreboard','movies'):
            match=re.search(r'^\['+section+r'\]\s*\r?\n(.*?)(?=^\[|\Z)',text,re.M|re.S|re.I)
            if match:
                lines=[line for line in match[1].splitlines() if '=' in line and line.split('=',1)[0].strip() and not line.lstrip().startswith((';','#'))]
                ini.read_string('['+section+']\n'+'\n'.join(lines))
    names={}
    for candidate in (narration_root(game)/'competition_names.json',):
        if candidate.exists():names.update(json.loads(candidate.read_text(encoding='utf8')))
    keys=dict(ini.items('comp')) if ini.has_section('comp') else {}
    for section in ('movies','Scoreboard'):
        if ini.has_section(section):
            for key,value in ini.items(section):
                keys.setdefault(key,value)
                label=value.split(',')[0].strip()
                if label and label.casefold() not in ('none','default'):names[key]=label
    return [dict(id=str(k),name=names.get(str(k),'Competição '+str(k))) for k in keys]

def choose_profile(profiles,competition,previous=None):
    matching=[p for p in profiles if str(competition) in [str(k) for k in p.get('competitions',[])]]
    if len(matching)>1:matching=[p for p in matching if p['name']!=previous] or matching
    return random.choice(matching) if matching else None
