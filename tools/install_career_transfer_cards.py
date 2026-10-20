"""Install the verified native transfer cards without launching applications."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
import pefile

ROOT=Path(__file__).resolve().parents[1]
GAME=Path('U:/fifa 16')
DEV=Path('U:/mods/FIFA Friends V12')
NATIVE=DEV/'ModCarrerMode/source/career_native'


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    artifacts=ROOT/'artifacts/career_transfer_cards'
    emulated=json.loads((artifacts/'native_emulation.json').read_text())
    layout=json.loads((artifacts/'layout_validation.json').read_text())
    assert emulated['passed'] and len(emulated['checks'])==12
    assert emulated['installed_image_sha256']==digest(GAME/'fifa16.bin')
    assert layout['passed'] and layout['unrelated_hub_nodes_unchanged']
    assert 'OK' in (artifacts/'layout_tests.log').read_text()
    assert 'PASS: ten top/latest transfers' in (artifacts/'native_wrapper_tests.log').read_text()
    assert 'PASS: all four transfer call sites validated' in (artifacts/'native_preflight_tests.log').read_text()
    dll=NATIVE/'build/production/dinput8.dll';raw=dll.read_bytes()
    assert all(name.encode() in raw for name in ('career_top_transfers','career_latest_transfers',
               'career_top_transfers_refresh','career_latest_transfers_refresh'))
    pe=pefile.PE(data=raw)
    protocol=next(s.address for s in pe.DIRECTORY_ENTRY_EXPORT.symbols if s.name==b'Fifa16CareerJobOfferProtocol')
    assert int.from_bytes(pe.get_data(protocol,4),'little')==1
    executables={str(base/'Server16Python.exe'):digest(base/'Server16Python.exe') for base in (GAME,DEV)}
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    files=[]
    def install(source,target,base):
        expected=digest(source)
        if target.exists() and digest(target)==expected:
            files.append({'target':str(target),'sha256':expected,'already_current':True});return
        backup=base/'runtime/backups/career_transfer_cards'/stamp/target.relative_to(base)
        backup.parent.mkdir(parents=True,exist_ok=True)
        old=digest(target) if target.exists() else None
        if old:
            shutil.copy2(target,backup);assert digest(backup)==old
        target.parent.mkdir(parents=True,exist_ok=True)
        loaded=None
        try:shutil.copy2(source,target)
        except OSError as exc:
            if getattr(exc,'winerror',None) not in (5,32,33,1224):raise
            loaded=backup.with_name(backup.name+'.loaded')
            assert loaded.resolve().is_relative_to(base.resolve())
            target.rename(loaded)
            try:shutil.copy2(source,target)
            except Exception:loaded.rename(target);raise
        assert digest(target)==expected
        files.append({'target':str(target),'sha256':expected,'before_sha256':old,
                      'backup':str(backup) if old else None,'loaded_previous_file':str(loaded) if loaded else None})
    for base in (GAME,DEV):
        install(ROOT/'native_mods/career_overlay/layout/careermanagerhubcfg.xml',base/'data/ui/layout/careermanagerhubcfg.xml',base)
        install(dll,base/'dinput8.dll',base)
    sources=('src/host/dinput8_wrapper.c','src/host/career_transfer_cards.h',
             'tests/providers/test_career_transfer_cards.c','tests/providers/test_career_transfer_preflight.c',
             'scripts/tests/test_career_transfer_cards.cmd','scripts/tests/test_career_transfer_preflight.cmd')
    for base,folder in ((GAME,'ModCarrerMode/source/career_native'),(ROOT,'native_mods/career_native')):
        for relative in sources:install(NATIVE/relative,base/folder/relative,base)
    for relative in ('expand_career_transfer_cards.py','validate_transfer_cards_native.py','install_career_transfer_cards.py'):
        install(ROOT/'tools'/relative,DEV/'ModCarrerMode/source/tools'/relative,DEV)
    install(ROOT/'tests/test_career_transfer_cards_layout.py',DEV/'ModCarrerMode/source/tests/test_career_transfer_cards_layout.py',DEV)
    install(ROOT/'docs/OVERLAY_CARREIRA.md',DEV/'ModCarrerMode/source/OVERLAY_CARREIRA.md',DEV)
    assert all(digest(Path(path))==sha for path,sha in executables.items())
    report={'passed':True,'installed_utc':stamp,'files':files,'top_rows':10,'latest_rows':10,
            'columns':2,'rows_per_column':5,'native_data_and_sorting_preserved':True,
            'native_emulation_cases':len(emulated['checks']),'server_executables_unchanged':True,
            'game_process_opened':False,'applications_restarted':False,'save_modified':False,
            'visual_in_game_verified':False,'requires_manual_fifa_restart':True}
    (artifacts/'install_report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({'passed':True,'verified_targets':len(files),'native_sha256':digest(dll),
                      'requires_manual_fifa_restart':True},indent=2))


if __name__=='__main__':main()
