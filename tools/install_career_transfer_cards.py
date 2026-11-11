"""Install the verified native transfer cards without launching applications."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
import pefile
from expand_career_transfer_cards import expand

ROOT=Path(__file__).resolve().parents[1]
GAME=Path('U:/fifa 16')
DEV=ROOT.parents[1]
NATIVE=DEV/'ModCarrerMode/source/career_native'


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    artifacts=ROOT/'artifacts/career_transfer_cards'
    emulated=json.loads((artifacts/'native_emulation.json').read_text())
    layout=json.loads((artifacts/'layout_validation.json').read_text())
    assert emulated['passed'] and len(emulated['checks'])==12
    assert all(emulated[k] for k in ('compiled_hook_executed',
        'native_selector_and_row_count_executed','native_param_serialization_executed',
        'shared_provider_no_collisions','shrinking_refresh_clears_stale_rows'))
    assert emulated['installed_image_sha256']==digest(GAME/'fifa16.bin')
    assert layout['passed'] and layout['unrelated_hub_nodes_unchanged']
    assert 'OK' in (artifacts/'layout_tests.log').read_text()
    assert 'PASS: ten top/latest transfers' in (artifacts/'native_wrapper_tests.log').read_text()
    assert 'PASS: all four transfer call sites validated' in (artifacts/'native_preflight_tests.log').read_text()
    dll=NATIVE/'build/production/dinput8.dll';raw=dll.read_bytes()
    assert emulated['native_dll_sha256']==digest(dll)
    assert all(name.encode() in raw for name in ('career_top_transfers','career_latest_transfers',
               'career_top_transfers_refresh','career_latest_transfers_refresh'))
    pe=pefile.PE(data=raw)
    protocol=next(s.address for s in pe.DIRECTORY_ENTRY_EXPORT.symbols if s.name==b'Fifa16CareerJobOfferProtocol')
    assert int.from_bytes(pe.get_data(protocol,4),'little')==1
    executables={str(base/'Server16Python.exe'):digest(base/'Server16Python.exe') for base in (GAME,DEV)}
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    files=[]
    def install(source,target,base,content=None):
        content=source.read_bytes() if content is None else content
        expected=hashlib.sha256(content).hexdigest()
        if target.exists() and digest(target)==expected:
            files.append({'target':str(target),'sha256':expected,'already_current':True});return
        backup=base/'runtime/backups/career_transfer_cards'/stamp/target.relative_to(base)
        backup.parent.mkdir(parents=True,exist_ok=True)
        old=digest(target) if target.exists() else None
        if old:
            shutil.copy2(target,backup);assert digest(backup)==old
        target.parent.mkdir(parents=True,exist_ok=True)
        assert target.resolve().is_relative_to(base.resolve())
        loaded=None
        temp=target.with_name(target.name+'.transfer-cards-new')
        temp.write_bytes(content)
        try:temp.replace(target)
        except OSError as exc:
            if getattr(exc,'winerror',None) not in (5,32,33,1224):raise
            loaded=backup.with_name(backup.name+'.loaded')
            assert loaded.resolve().is_relative_to(base.resolve())
            target.rename(loaded)
            try:temp.replace(target)
            except Exception:loaded.rename(target);raise
        assert digest(target)==expected
        files.append({'target':str(target),'sha256':expected,'before_sha256':old,
                      'backup':str(backup) if old else None,'loaded_previous_file':str(loaded) if loaded else None})
    for base in (GAME,DEV):
        # Runtime and authoring layouts contain other independent cards. Only
        # replace the two transfer subtiles, preserving each target's content.
        target=base/'data/ui/layout/careermanagerhubcfg.xml'
        install(target,target,base,expand(target.read_text(encoding='utf8')).encode('utf8'))
        install(artifacts/'transferinfo.big',base/'data/ui/game/components/FluxComponents/career/TransferInfo.big',base)
        install(dll,base/'dinput8.dll',base)
    sources=('src/host/dinput8_wrapper.c','src/host/career_transfer_cards.h',
             'tests/providers/test_career_transfer_cards.c','tests/providers/test_career_transfer_preflight.c',
             'scripts/tests/test_career_transfer_cards.cmd','scripts/tests/test_career_transfer_preflight.cmd')
    for relative in sources:
        install(NATIVE/relative,GAME/'ModCarrerMode/source/career_native'/relative,GAME)
    for relative in ('expand_career_transfer_cards.py','validate_transfer_cards_native.py','install_career_transfer_cards.py'):
        install(ROOT/'tools'/relative,GAME/'ModCarrerMode/source/tools'/relative,GAME)
    for relative in ('tests/test_career_transfer_cards_layout.py',
        'native_mods/career_overlay/layout/careermanagerhubcfg.xml',
        'tools/career_branding/originals/transferinfo.big'):
        install(ROOT/relative,GAME/'ModCarrerMode/source'/relative,GAME)
    assert all(digest(Path(path))==sha for path,sha in executables.items())
    report={'passed':True,'installed_utc':stamp,'files':files,'top_rows':10,'latest_rows':10,
            'columns':2,'rows_per_column':5,'native_data_and_sorting_preserved':True,
            'row_major_order':True,'native_transfer_component_restyled':True,
            'native_emulation_cases':len(emulated['checks']),'server_executables_unchanged':True,
            'game_process_opened':False,'applications_restarted':False,'save_modified':False,
            'visual_in_game_verified':False,'requires_manual_fifa_restart':True}
    (artifacts/'install_report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({'passed':True,'verified_targets':len(files),'native_sha256':digest(dll),
                      'requires_manual_fifa_restart':True},indent=2))


if __name__=='__main__':main()
