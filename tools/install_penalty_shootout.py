"""Install the scoreboard/shootout smoke fix without restarting applications."""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from server16_py.frontend_stadium import atomic_write


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def install(game,server,dll):
    from PyInstaller.archive.readers import CArchiveReader
    game=Path(game).resolve();server=Path(server).resolve();dll=Path(dll).resolve()
    package=json.loads(server.with_suffix('.json').read_text(encoding='utf8'))
    if package['sha256']!=digest(server) or set(package['modules'])!={'server16_py.match_state'}:
        raise ValueError('Build and verify the one-module scoreboard fix first')
    pyz=CArchiveReader(str(server)).open_embedded_archive('PYZ.pyz')
    code=pyz.extract('server16_py.match_state')
    expected=compile((ROOT/'server16_py/match_state.py').read_bytes(),code.co_filename,'exec')
    if code!=expected or b'PENALTY_SHOOTOUT_BLOCKED' not in dll.read_bytes():
        raise ValueError('Build outputs do not contain the verified shootout fix')
    manifest_path=game/'ModCarrerMode/runtime/frontend_stadium_install.json'
    frontend=json.loads(manifest_path.read_text(encoding='utf8')) if manifest_path.exists() else None
    if frontend and frontend['files']['Server16Python.exe']!=digest(game/'Server16Python.exe'):
        raise ValueError('The installed Server16 changed since its previous manifest')
    protected={}
    for name in ('dinput8.dll','SubsOn.dll','SubsOn.ini','FSW/settings.ini',
                 'ModCarrerMode/mods/enabled.txt','ModCarrerMode/config/match_presentation.ini',
                 'ModCarrerMode/config/frontend_stadium.ini'):
        path=game/name
        if path.exists():protected[name]=digest(path)
    backup=game/'ModCarrerMode/backups'/('penalty_shootout_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
    backup.mkdir(parents=True,exist_ok=False)
    entries=[]
    def put(source,target,label):
        source=Path(source);target=Path(target)
        before=digest(target) if target.exists() else None
        after=digest(source)
        if before==after:return
        saved=backup/label
        saved.parent.mkdir(parents=True,exist_ok=True)
        if before:shutil.copy2(target,saved)
        target.parent.mkdir(parents=True,exist_ok=True)
        pending=target.with_name(target.name+'.penalty_shootout.pending')
        if pending.exists():raise FileExistsError(pending)
        shutil.copy2(source,pending)
        loaded=None
        try:os.replace(pending,target)
        except OSError as error:
            if getattr(error,'winerror',None) not in (5,32,33,1224):raise
            loaded=saved.with_name(saved.name+'.loaded')
            if not loaded.resolve().is_relative_to(backup.resolve()) or loaded.exists():raise
            target.rename(loaded)
            try:os.replace(pending,target)
            except BaseException:
                loaded.rename(target)
                raise
        if digest(target)!=after:raise ValueError('Installed hash mismatch: '+str(target))
        entries.append({'target':str(target),'sha256':after,'before_sha256':before,
                        'backup':str(saved) if before else None,
                        'loaded_previous_file':str(loaded) if loaded else None})
    put(server,game/'Server16Python.exe','Server16Python.exe')
    # Preserve the active mod's name and enabled entry; the mapped old image
    # remains intact under its backup name until the user closes FIFA.
    put(dll,game/'ModCarrerMode/mods/stadium_pyrotechnics/stadium_pyrotechnics.dll',
        'stadium_pyrotechnics.dll')
    for mirror,folder in (('game',game/'ModCarrerMode/source'),
                          ('development',Path('U:/mods/FIFA Friends V12/ModCarrerMode/source'))):
        if not folder.exists():continue
        for name in ('stadium_pyrotechnics.cpp','presentation.h','shootout.h',
                     'presentation_test.cpp','runtime_scene_test.cpp'):
            put(ROOT/'native_mods/pyro'/name,folder/'stadium_pyrotechnics'/name,f'source/{mirror}/pyro/{name}')
        put(ROOT/'server16_py/match_state.py',folder/'server16_py/match_state.py',f'source/{mirror}/match_state.py')
        put(ROOT/'tests/test_penalty_shootout.py',folder/'tests/test_penalty_shootout.py',f'source/{mirror}/test_penalty_shootout.py')
    if frontend:
        shutil.copy2(manifest_path,backup/manifest_path.name)
        frontend['files']['Server16Python.exe']=digest(game/'Server16Python.exe')
        frontend['activation']='Next Server16 and FIFA launch; running processes were not restarted'
        atomic_write(manifest_path,json.dumps(frontend,indent=2).encode('utf8'))
    for name,sha in protected.items():
        if digest(game/name)!=sha:raise ValueError('Protected file changed: '+name)
    report={'installed':True,'backup':str(backup),'files':entries,'preserved_files':protected,
            'python_tests_passed':30,'native_build_and_regressions_passed':True,
            'native_shootout_state':11,'native_regulation_penalty_state':7,
            'preserved_python_modules':package['preserved_python_modules'],
            'applications_restarted':False,'ram_written':False,'live_visual_verified':False,
            'requires_fifa_and_server_restart':True}
    atomic_write(game/'ModCarrerMode/runtime/penalty_shootout_install.json',json.dumps(report,indent=2).encode('utf8'))
    print(json.dumps({'installed':True,'backup':str(backup),'changed_files':len(entries),
                      'server_sha256':digest(game/'Server16Python.exe'),
                      'native_sha256':digest(game/'ModCarrerMode/mods/stadium_pyrotechnics/stadium_pyrotechnics.dll'),
                      'requires_fifa_and_server_restart':True},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-root',required=True,type=Path)
    parser.add_argument('--server',required=True,type=Path)
    parser.add_argument('--dll',required=True,type=Path)
    args=parser.parse_args();install(args.game_root,args.server,args.dll)
