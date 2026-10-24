import ctypes
import os
import sys
from pathlib import Path

_vendor=Path(__file__).resolve().parent/'vendor'
if _vendor.is_dir():sys.path.insert(0,str(_vendor))


def _set_windows_app_id():
    if os.name != "nt":
        return
    try:
        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        set_app_id = shell32.SetCurrentProcessExplicitAppUserModelID
        set_app_id.argtypes = [ctypes.c_wchar_p]
        set_app_id.restype = ctypes.c_long
        set_app_id("Igor1043.CGFS16.Server16Python")
    except Exception:
        pass


def _start_splash():
    try:
        from server16_py.splash import SplashScreen, enable_dpi_awareness

        enable_dpi_awareness()
        return SplashScreen()
    except Exception:
        return None


if __name__ == "__main__":
    import sys
    if '--server16-selftest' in sys.argv:
        from server16_py.build_check import run
        raise SystemExit(run(sys.argv[sys.argv.index('--server16-selftest')+1]))
    if '--activate-career-ui' in sys.argv or '--activate-panorama-ui' in sys.argv:
        import argparse,json
        from pathlib import Path
        from server16_py.loose_ui import activate,PANORAMA_TARGETS
        parser=argparse.ArgumentParser();mode=parser.add_mutually_exclusive_group(required=True);mode.add_argument('--activate-career-ui',action='store_true');mode.add_argument('--activate-panorama-ui',action='store_true');parser.add_argument('--game-root',type=Path,required=True);parser.add_argument('--verify-only',action='store_true')
        args=parser.parse_args();result=activate(args.game_root,args.verify_only,PANORAMA_TARGETS if args.activate_panorama_ui else None)
        target=args.game_root/('ModCarrerMode/runtime/panorama_ui_activation.json' if args.activate_panorama_ui else 'ModCarrerMode/runtime/club_environment/ui_activation.json');target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(result),encoding='utf8')
        raise SystemExit(0 if result['status']=='ready' else 2)
    if any(arg in sys.argv for arg in ('--club-environment','--club-environment-worker','--club-environment-check','--club-environment-install')):
        from server16_py.club_environment import main as run_club_environment
        raise SystemExit(run_club_environment())
    _set_windows_app_id()
    splash = _start_splash()
    try:
        from server16_py.app import main

        main(splash=splash)
    except BaseException:
        if splash is not None:
            splash.close()
        raise
