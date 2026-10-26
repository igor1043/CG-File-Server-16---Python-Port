"""Read-only frozen-build smoke check: no Tk, process attachment or driver install."""
from pathlib import Path
import importlib
import importlib.util
import json
import sys


def run(output):
    from . import __version__
    root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))
    modules=('sqlite3','numpy','PIL.Image','psutil','server16_py.app','server16_py.club_environment',
             'server16_py.career_context','server16_py.frontend_stadium','server16_py.gamepad_panel',
             'server16_py.stadium_match_assets','server16_py.match_state',
             'server16_py.extra_scenes_panel')
    result={'version':__version__,'frozen':bool(getattr(sys,'frozen',False)),'modules':{},'binaries':{},'ok':True}
    for name in modules:
        try:importlib.import_module(name);result['modules'][name]='ok'
        except Exception as e:result['modules'][name]=str(e);result['ok']=False
    for name in ('cgfs16_overlay.dll','fifa16_narration.dll','server16_first_person_v14.dll','FifaLibrary16.dll','career_jobs_runtime.dll'):
        p=root/'bin'/name;result['binaries'][name]=p.exists()
        if not p.exists():result['ok']=False
    result['external_overlay_injector_absent']=not (root/'bin/cgfs16_inject.exe').exists()
    result['ok']=result['ok'] and result['external_overlay_injector_absent']
    result['gamepad_package_present']=importlib.util.find_spec('vgamepad') is not None
    result['vigem_client_present']=(root/'vgamepad/win/vigem/client/x64/ViGEmClient.dll').exists()
    result['vigem_installer_present']=(root/'vgamepad/win/vigem/install/x64/ViGEmBusSetup_x64.msi').exists()
    result['hidhide_installer_present']=any((root/'bin/HidHide').glob('*.exe'))
    result['ok']=result['ok'] and all(result[key] for key in ('gamepad_package_present','vigem_client_present','vigem_installer_present','hidhide_installer_present'))
    Path(output).write_text(json.dumps(result,indent=2),encoding='utf8')
    return 0 if result['ok'] else 2
