"""Explicit custom-stadium capacity/attendance; no borrowed native-slot data."""
from pathlib import Path
import configparser,re,unicodedata

def count(value):
    value=str(value or '').strip()
    if not re.fullmatch(r'(?:\d+|\d{1,3}(?:[., ]\d{3})+)',value):return None
    number=int(re.sub(r'[., ]','',value))
    return number if 0<=number<=2_000_000 else None

def load(path):
    parser=configparser.ConfigParser(interpolation=None,strict=False)
    if not path.is_file():return parser
    raw=path.read_bytes()
    for encoding in ('utf-8-sig','utf-16','cp1252'):
        try:parser.read_string(raw.decode(encoding));return parser
        except (UnicodeError,configparser.Error):parser=configparser.ConfigParser(interpolation=None,strict=False)
    return parser

def folded(value):return unicodedata.normalize('NFC',value).strip().casefold()
def section(parser,name):return next((s for s in parser.sections() if folded(s)==folded(name)),None)
def read_custom_metadata(game,name,package):
    sources=[];settings=load(Path(game)/'FSW/settings.ini')
    for key in ('capacity','attendance'):
        s=section(settings,'stadium'+key)
        if s:
            option=next((k for k in settings[s] if folded(k)==folded(name)),None)
            if option:sources.append((key,settings[s][option],'FSW/settings.ini ['+s+']'))
    for filename in ('metadata.ini','stadium.ini'):
        p=Path(package)/filename;parser=load(p);s=section(parser,name) or section(parser,'stadium')
        if s:
            identity=parser[s].get('name','').strip()
            if identity and folded(identity)!=folded(name):continue
            for key in ('capacity','attendance'):
                if key in parser[s]:sources.append((key,parser[s][key],filename+' ['+s+']'))
    parser=load(Path(game)/'ModCarrerMode/config/stadium_metadata.ini');s=section(parser,name)
    if s:
        for key in ('capacity','attendance'):
            if key in parser[s]:sources.append((key,parser[s][key],'ModCarrerMode/config/stadium_metadata.ini ['+s+']'))
    result={'capacity':None,'attendance':None,'metadata_sources':{}}
    for key,value,origin in sources:
        parsed=count(value)
        if parsed is not None and (key!='capacity' or parsed>0):result[key]=parsed;result['metadata_sources'][key]=origin
    if result['capacity'] is not None and result['attendance'] is not None and result['attendance']>result['capacity']:
        result['attendance']=None;result['metadata_sources'].pop('attendance',None)
    return result
