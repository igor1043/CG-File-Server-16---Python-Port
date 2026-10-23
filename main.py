import ctypes
import os


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
    if '--activate-career-ui' in sys.argv:
        import argparse,json
        from pathlib import Path
        from server16_py.loose_ui import activate
        parser=argparse.ArgumentParser();parser.add_argument('--activate-career-ui',action='store_true');parser.add_argument('--game-root',type=Path,required=True);parser.add_argument('--verify-only',action='store_true')
        args=parser.parse_args();result=activate(args.game_root,args.verify_only)
        target=args.game_root/'ModCarrerMode/runtime/club_environment/ui_activation.json';target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(result),encoding='utf8')
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
