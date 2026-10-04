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
    _set_windows_app_id()
    splash = _start_splash()
    try:
        from server16_py.app import main

        main(splash=splash)
    except BaseException:
        if splash is not None:
            splash.close()
        raise
