"""Preferences for the menu panorama, independent of match assignments."""
from pathlib import Path
import configparser
import io
import time
from .ini_file import IniFile,SessionIniFile
from .stadium_catalog import StadiumEntry

def frontend_page(page):
    page=(page or '').lower()
    return page.endswith(('/fluxhub','/selectfavoriteteam','/profile','/stadiumpan'))

def enabled(game):
    value=SessionIniFile(Path(game)/'ModCarrerMode/config/frontend_stadium.ini').read('enabled','frontend_stadium').strip()
    return value.casefold() in ('1','true','yes','on')


def selection(game,team=0,*,career=False,session=0):
    settings=SessionIniFile(Path(game)/'ModCarrerMode/config/frontend_stadium.ini')
    if career:
        # Manual career choices last only for this entry into this save/club.
        if (session and settings.read('session','frontend_stadium_career')==str(session)
                and settings.read('team','frontend_stadium_career')==str(team)):
            return settings.read('selection','frontend_stadium_career').strip() or 'auto'
        return 'auto'
    if team:
        return settings.read(str(team),'frontend_stadium_clubs').strip() or 'auto'
    return settings.read('selected_stadium','frontend_stadium').strip() or 'auto'

def _save(parser,config):
    if not parser.has_section('frontend_stadium'):parser.add_section('frontend_stadium')
    parser.set('frontend_stadium','reload_revision',str(time.time_ns()%2147483647))
    output=io.StringIO();parser.write(output)
    from .frontend_stadium import atomic_write
    atomic_write(config.path,output.getvalue().encode('utf8'))


def save_enabled(game,value):
    config=IniFile(Path(game)/'ModCarrerMode/config/frontend_stadium.ini')
    parser=config._load()
    if not parser.has_section('frontend_stadium'):parser.add_section('frontend_stadium')
    parser.set('frontend_stadium','enabled','1' if value else '0')
    _save(parser,config)


def save_selection(game,name,team=0,*,career=False,session=0):
    if not name or '/' in name or '\\' in name or name in ('.','..'):raise ValueError('Invalid stadium selection')
    config=IniFile(Path(game)/'ModCarrerMode/config/frontend_stadium.ini')
    parser=config._load()
    if career and (not team or not session):raise ValueError('Career session is no longer active')
    section='frontend_stadium_career' if career else 'frontend_stadium_clubs' if team else 'frontend_stadium'
    actual=config._resolve_section_name(parser,section) or section
    if not parser.has_section(actual):parser.add_section(actual)
    if career:
        parser.set(actual,'team',str(team));parser.set(actual,'session',str(session))
        parser.set(actual,'selection',name)
    else:parser.set(actual,str(team) if team else 'selected_stadium',name)
    _save(parser,config)

def live_state(game):
    try:
        parser=configparser.ConfigParser(interpolation=None)
        parser.read_string((Path(game)/'ModCarrerMode/runtime/frontend_stadium_live.ini').read_text(encoding='utf16'))
        return {key:parser.getint('frontend_stadium',key,fallback=0) for key in ('pid','phase','team','career','session','slot','error','request')}
    except (OSError,UnicodeError,ValueError,configparser.Error):return {}

def automatic_entry(game):
    return StadiumEntry('auto','','Automático pelo clube','Favorito no início; clube ativo na carreira','',Path(game),None)
