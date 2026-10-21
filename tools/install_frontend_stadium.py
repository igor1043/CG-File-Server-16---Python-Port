"""Install the experimental FE stadium bridge with reversible source backups."""
import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from server16_py.frontend_stadium import atomic_write, LUA_MARKER


def patched_stadium(source):
    if LUA_MARKER in source:
        raise ValueError('This stadium.lua already contains the frontend patch; restore its recorded backup before reinstalling')
    anchors = {
        '\tGoalNetUpdate(idx*2)': '\tServer16FrontendUpdate(idx)\n\tGoalNetUpdate(idx*2)',
        'function GetRMStadModel(idx)': 'function GetRMStadModel(idx)\n\tlocal server16 = Server16FrontendModel(idx)\n\tif server16 ~= "" then return server16 end',
        'function GetRMStadTex(idx)': 'function GetRMStadTex(idx)\n\tlocal server16 = Server16FrontendTexture(idx)\n\tif server16 ~= "" then return server16 end',
    }
    for before,after in anchors.items():
        if source.count(before)!=1:
            raise ValueError('Unrecognized stadium.lua anchor: '+before)
        source=source.replace(before,after)
    prefix=LUA_MARKER+'\nlocal server16FrontendScript = gSportsRNA:LoadScriptAsync("data/fifarna/lua/assets/server16_frontend_stadium.lua")\ngSportsRNA:LoadScriptAsyncComplete(server16FrontendScript)\n\n'
    return prefix+source


def patched_crowd(source):
    if LUA_MARKER in source:raise ValueError('crowd.lua already contains this frontend patch')
    anchors={
        'db.crowd[idx].stadiumID = as:GetInt(state, "wvAttribStadID")':
            'db.crowd[idx].stadiumID = as:GetInt(state, "wvAttribStadID")\n\tServer16FrontendCrowdUpdate(idx)',
        'function GetRMChairMod(idx)':
            'function GetRMChairMod(idx)\n\tlocal server16 = Server16FrontendChair(idx)\n\tif server16 ~= "" then return server16 end',
    }
    for before,after in anchors.items():
        if source.count(before)!=1:raise ValueError('Unrecognized crowd.lua anchor: '+before)
        source=source.replace(before,after)
    return LUA_MARKER+'\nif not Server16FrontendCrowdUpdate then\n local script = gSportsRNA:LoadScriptAsync("data/fifarna/lua/assets/server16_frontend_stadium.lua")\n gSportsRNA:LoadScriptAsyncComplete(script)\nend\n'+source


def patched_hub_background(source,state):
    """Use the stadium-aware component, retaining BOOTFLOW as its fallback."""
    import re
    anchor=list(re.finditer(r'"name"\s*:\s*"'+re.escape(state)+r'"',source))
    if len(anchor)!=1:raise ValueError('Ambiguous hub state: '+state)
    start=source.index('"onEnter"',anchor[0].end())
    end=source.index('"onExit"',start)
    if end-start>6000:raise ValueError('Unrecognized hub entry: '+state)
    entry=source[start:end]
    pattern=r'\[\s*"loadView"\s*,\s*\[\s*"background"\s*,\s*"BOOTFLOW"\s*\]\s*\]'
    replacement='["loadView",["background", "FIFA", "BOOTFLOW"]]'
    if replacement in entry:return source
    entry,count=re.subn(pattern,replacement,entry)
    if count!=1:raise ValueError('Unrecognized hub background: '+state)
    return source[:start]+entry+source[end:]


def install(game,dll,helper,activate=False,ui=None,server=None):
    game=game.resolve()
    import psutil
    locked={'fifa16.exe','server16python.exe'} if server else {'fifa16.exe'}
    if any((p.info['name'] or '').lower() in locked for p in psutil.process_iter(['name'])):
        raise RuntimeError('Close FIFA and Server16 before installing the next frontend version')
    if ui and any(not (ui/name).is_file() for name in ('backgroundfifa.big','stadiumpan.big')):
        raise FileNotFoundError('Build both frontend UI components before installation')
    nav_changes={}
    if ui:
        for relative,state in [('data/ui/nav/mainfeflow.nav','mainMenuWithStadium'),
                               ('data/ui/nav/careermode/mainmenuhubflow.nav','MainMenuHub')]:
            path=game/relative
            nav_changes[relative]=(path.read_bytes(),patched_hub_background(path.read_text(encoding='utf-8-sig'),state).encode('utf8'))
    if server and (not server.is_file() or server.read_bytes()[:2]!=b'MZ'):
        raise ValueError('Build the Server16 executable before installation')
    source_path=game/'data/fifarna/lua/assets/stadium.lua'
    original=source_path.read_bytes()
    previous=original
    record_path=game/'ModCarrerMode/runtime/frontend_stadium_install.json'
    if LUA_MARKER.encode() in original:
        record=json.loads(record_path.read_text())
        expected=record['files'][str(source_path.relative_to(game))]
        if hashlib.sha256(original).hexdigest()!=expected:raise ValueError('stadium.lua changed outside this mod')
        original=(Path(record['backup'])/'stadium.lua').read_bytes()
    modified=patched_stadium(original.decode('utf-8-sig'))
    crowd_path=game/'data/fifarna/lua/assets/crowd.lua'
    crowd_original=crowd_path.read_bytes()
    crowd_previous=crowd_original
    if LUA_MARKER.encode() in crowd_original:
        record=json.loads(record_path.read_text())
        expected=record['files'][str(crowd_path.relative_to(game))]
        if hashlib.sha256(crowd_original).hexdigest()!=expected:raise ValueError('crowd.lua changed outside this mod')
        crowd_original=(Path(record['backup'])/'crowd.lua').read_bytes()
    crowd_modified=patched_crowd(crowd_original.decode('utf-8-sig'))
    if not dll.is_file() or not helper.is_file():raise FileNotFoundError('Build the native module and helper first')
    if dll.read_bytes()[:2]!=b'MZ' or helper.read_bytes()[:2]!=b'MZ':raise ValueError('Invalid PE build')
    stamp=datetime.now().strftime('%Y%m%d_%H%M%S')
    backup=game/'ModCarrerMode/backups'/('frontend_stadium_'+stamp)
    backup.mkdir(parents=True)
    (backup/'stadium.lua').write_bytes(original)
    (backup/'stadium.before.lua').write_bytes(previous)
    (backup/'crowd.lua').write_bytes(crowd_original)
    (backup/'crowd.before.lua').write_bytes(crowd_previous)
    enabled=game/'ModCarrerMode/mods/enabled.txt'
    enabled_before=enabled.read_bytes()
    (backup/'enabled.txt').write_bytes(enabled_before)
    config=game/'ModCarrerMode/config/frontend_stadium.ini'
    if config.is_file():shutil.copy2(config,backup/'frontend_stadium.ini')
    assets=source_path.parent
    atomic_write(assets/'server16_frontend_stadium.lua',(ROOT/'native_mods/frontend_stadium/frontend_stadium.lua').read_bytes())
    for slot in (176,261):
        atomic_write(assets/f'server16_frontend_{slot}.lua',f'Server16FrontendRoutes = Server16FrontendRoutes or {{}}\nServer16FrontendRoutes[{slot}] = nil\n'.encode())
    target_dll=game/'ModCarrerMode/mods/frontend_stadium/frontend_stadium_native_v11.dll'
    target_helper=game/'ModCarrerMode/tools/frontend_stadium_prepare.exe'
    for src,dst in ((dll,target_dll),(helper,target_helper)):
        dst.parent.mkdir(parents=True,exist_ok=True)
        if dst.exists():shutil.copy2(dst,backup/dst.name)
        shutil.copy2(src,dst)
    ui_record={}
    if ui:
        for filename,relative in [('backgroundfifa.big','data/ui/game/background/backgroundfifa.big'),('stadiumpan.big','data/ui/game/screens/misc/stadiumpan.big')]:
            dst=game/relative
            ui_record[relative]={'existed':dst.is_file(),'backup':str(backup/filename)}
            if dst.is_file():shutil.copy2(dst,backup/filename)
            atomic_write(dst,(ui/filename).read_bytes())
        for relative,(before,after) in nav_changes.items():
            saved=backup/Path(relative).name
            saved.write_bytes(before)
            ui_record[relative]={'existed':True,'backup':str(saved)}
            atomic_write(game/relative,after)
    if server:
        target=game/'Server16Python.exe'
        shutil.copy2(target,backup/'Server16Python.exe')
        shutil.copy2(server,target)
    config.parent.mkdir(parents=True,exist_ok=True)
    if not config.exists():shutil.copy2(ROOT/'native_mods/frontend_stadium/frontend_stadium.ini',config)
    if activate:
        from server16_py.ini_file import IniFile
        IniFile(config).write('enabled','1','frontend_stadium')
    # Migrate the former global preference to the club for which it was saved.
    from server16_py.frontend_stadium_selection import selection,save_selection
    legacy=selection(game)
    if legacy!='auto':
        last_path=game/'ModCarrerMode/runtime/frontend_stadium_last.json'
        if last_path.exists():
            team=int(json.loads(last_path.read_text(encoding='utf8')).get('team',0))
            if team and selection(game,team)=='auto':save_selection(game,legacy,team)
        from server16_py.ini_file import IniFile
        IniFile(config).write('selected_stadium','auto','frontend_stadium')
    atomic_write(source_path,modified.encode('utf8'))
    atomic_write(crowd_path,crowd_modified.encode('utf8'))
    line='frontend_stadium\\frontend_stadium_native_v11.dll'
    text=enabled_before.decode('utf-8-sig')
    owned={f'frontend_stadium\\frontend_stadium_native_v{v}.dll' for v in range(1,12)}
    text='\r\n'.join(s for s in text.splitlines() if s.strip().casefold() not in owned)
    atomic_write(enabled,(text.rstrip()+'\r\n'+line+'\r\n').encode('utf8'))
    source_dir=game/'ModCarrerMode/source/frontend_stadium'
    source_dir.mkdir(parents=True,exist_ok=True)
    for src in (ROOT/'native_mods/frontend_stadium').glob('*'):
        if src.is_file():shutil.copy2(src,source_dir/src.name)
    installed_paths=[target_dll,target_helper,source_path,crowd_path,assets/'server16_frontend_stadium.lua']
    installed_paths.extend(game/relative for relative in ui_record)
    if (game/'Server16Python.exe').is_file():installed_paths.append(game/'Server16Python.exe')
    report={'version':11,'experimental':True,'game':str(game),'backup':str(backup),'ui':ui_record,
            'requires_restart':True,'files':{str(path.relative_to(game)):hashlib.sha256(path.read_bytes()).hexdigest()
             for path in installed_paths}}
    atomic_write(game/'ModCarrerMode/runtime/frontend_stadium_install.json',json.dumps(report,indent=2).encode())
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-root',type=Path,required=True)
    parser.add_argument('--dll',type=Path,required=True)
    parser.add_argument('--helper',type=Path,required=True)
    parser.add_argument('--enable',action='store_true')
    parser.add_argument('--ui',type=Path)
    parser.add_argument('--server',type=Path)
    args=parser.parse_args();install(args.game_root,args.dll,args.helper,args.enable,args.ui,args.server)
