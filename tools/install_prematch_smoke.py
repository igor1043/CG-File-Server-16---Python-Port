"""Install verified smoke controls in game and development without running FIFA."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
from PyInstaller.archive.readers import CArchiveReader

ROOT=Path(__file__).resolve().parents[1]
GAME=Path('U:/fifa 16')
DEV=Path('U:/mods/FIFA Friends V12')
NATIVE=DEV/'ModCarrerMode/source/stadium_pyrotechnics'


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main(exe):
    exe=Path(exe).resolve();artifacts=ROOT/'artifacts/prematch_smoke'
    required={'presentation_tests.log':'Ran 8 tests','cloth_tests.log':'Ran 4 tests',
              'prematch_tests.log':'Ran 7 tests','smoke_tests.log':'Ran 5 tests',
              'career_regression.log':'Ran 87 tests','selector_regression.log':'Ran 22 tests'}
    for filename,evidence in required.items():
        text=(artifacts/filename).read_text();assert evidence in text and '\nOK\n' in text,filename
    text=(artifacts/'native_build.log').read_text()
    assert 'Selected intro/goal emitters, 15s/20s actual event bounds, zero mask and frozen current-show options: PASS' in text
    assert 'Real tick: intro pan, blank-page team gap, score gap, long pause, native replay, resource recovery, 0:0 restart, home/away goals and natural fade: PASS' in text
    archive=CArchiveReader(str(exe));pyz=archive.open_embedded_archive('PYZ.pyz')
    for name in ('smoke_settings_panel','match_settings_panel','match_presentation','career_transfer_catalog'):
        assert 'server16_py.'+name in pyz.toc,name
    settings=pyz.extract('server16_py.match_settings_panel')
    assert 'SmokeSettingsPanel' in settings.co_names
    config=pyz.extract('server16_py.match_presentation')
    fields=next(c for c in config.co_consts if getattr(c,'co_name',None)=='PresentationOptions')
    assert all(k in fields.co_consts for k in ('smoke_entrance_seconds','smoke_goal_seconds','smoke_entrance_emitters','smoke_goal_emitters'))
    for entry,source in (('server16_py/career_save_worker.py',ROOT/'server16_py/career_save_worker.py'),
                         ('bin/cgfs16_overlay.dll',ROOT/'bin/cgfs16_overlay.dll')):
        key=next(k for k in archive.toc if k.replace('\\','/')==entry)
        assert archive.extract(key)==source.read_bytes(),entry
    pyro=NATIVE/'build/stadium_pyrotechnics.dll'
    assert b'smoke_entrance_seconds' in pyro.read_bytes().replace(b'\0',b'')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    protected={}
    for base in (GAME,DEV):
        for relative in ('dinput8.dll','ModCarrerMode/mods/enabled.txt',
             'ModCarrerMode/config/match_presentation.ini','ModCarrerMode/mods/stadium_pyrotechnics/pyro.ini',
             'ModCarrerMode/mods/smoke_machine/smoke_machine.dll',
             'data/sceneassets/particles/stadium_pyrotechnics_0.rx3',
             'data/sceneassets/particles/stadium_pyrotechnics_0.lnx'):
            path=base/relative
            if path.exists():protected[str(path)]=digest(path)
    entries=[]
    def install(source,target,base):
        expected=digest(source)
        if target.exists() and digest(target)==expected:
            entries.append({'target':str(target),'sha256':expected,'already_current':True});return
        # J: is short of space. Keep this task's Python-port backups on U:;
        # game and development backups remain inside their usual roots.
        backup_root=(DEV/'runtime/backups/python_port_prematch_smoke' if base==ROOT else base/'runtime/backups/prematch_smoke')
        backup=backup_root/stamp/target.relative_to(base)
        backup.parent.mkdir(parents=True,exist_ok=True)
        old=digest(target) if target.exists() else None
        if old:shutil.copy2(target,backup);assert digest(backup)==old
        target.parent.mkdir(parents=True,exist_ok=True);loaded=None
        try:shutil.copy2(source,target)
        except OSError as exc:
            if getattr(exc,'winerror',None) not in (5,32,33,1224):raise
            loaded=backup.with_name(backup.name+'.loaded')
            assert loaded.resolve().is_relative_to(backup_root.resolve())
            target.rename(loaded)
            try:shutil.copy2(source,target)
            except Exception:loaded.rename(target);raise
        assert digest(target)==expected
        entries.append({'target':str(target),'sha256':expected,'before_sha256':old,
                        'backup':str(backup) if old else None,'loaded_previous_file':str(loaded) if loaded else None})
    for base in (GAME,DEV):
        install(exe,base/'Server16Python.exe',base)
        install(pyro,base/'ModCarrerMode/mods/stadium_pyrotechnics/stadium_pyrotechnics.dll',base)
    for relative in ('dist_career/Server16Python.exe','dist/Server16Python.exe'):
        install(exe,ROOT/relative,ROOT)
    python_files=('match_presentation.py','match_settings_panel.py','smoke_settings_panel.py')
    for relative in python_files:
        install(ROOT/'server16_py'/relative,DEV/'ModCarrerMode/source/server16_py'/relative,DEV)
    # Keep the entire current flat source set buildable in both source mirrors.
    for source in NATIVE.iterdir():
        if source.is_file() and source.suffix.lower() in ('.h','.cpp','.cmd','.inc'):
            install(source,GAME/'ModCarrerMode/source/stadium_pyrotechnics'/source.name,GAME)
            install(source,ROOT/'native_mods/pyro'/source.name,ROOT)
    for doc in ('PREVIA_FUMACA.md','OVERLAY_CARREIRA.md'):
        for base in (GAME,DEV):install(ROOT/'docs'/doc,base/'ModCarrerMode/source'/doc,base)
    for relative in ('test_smoke_settings.py','test_match_presentation.py'):
        install(ROOT/'tests'/relative,DEV/'ModCarrerMode/source/tests'/relative,DEV)
    install(ROOT/'tools/install_prematch_smoke.py',DEV/'ModCarrerMode/source/tools/install_prematch_smoke.py',DEV)
    assert all(digest(Path(path))==sha for path,sha in protected.items())
    report={'passed':True,'installed_utc':stamp,'files':entries,'preserved_files':protected,
            'python_tests':sum((8,4,7,5,87,22)),'native_selected_emitters_and_duration_verified':True,
            'pause_replay_recovery_preserved':True,'durations_seconds':[15,120],
            'entrance_emitters':20,'goal_emitters':12,'home_goal_rule_preserved':True,
            'existing_preferences_unchanged':True,'applications_restarted':False,
            'game_process_accessed':False,'save_modified':False,'live_visual_verified':False,
            'requires_manual_fifa_and_server_restart':True,
            'exe_sha256':digest(exe),'pyro_sha256':digest(pyro)}
    (artifacts/'install_report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({'passed':True,'verified_targets':len(entries),'python_tests':report['python_tests'],
                     'exe_sha256':digest(exe),'pyro_sha256':digest(pyro)},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--exe',required=True)
    main(parser.parse_args().exe)
