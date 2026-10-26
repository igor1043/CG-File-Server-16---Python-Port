# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs


project_root = Path(SPECPATH)
sys.path.insert(0,str(project_root/'vendor'))
sys.path.insert(0,str(project_root/'scripts'))
from frozen_payload import bridge_files
import os

class ServerEXE(EXE):
    def _bootloader_file(self,exe,extension=None):
        filename=Path(super()._bootloader_file(exe,extension)).name
        directory=Path(os.environ.get('SERVER16_BOOTLOADER_DIR',project_root/'build/archive-bootloader/pyinstaller-6.20.0/PyInstaller/bootloader/Windows-64bit-intel'))
        target=directory/filename
        if not target.is_file():raise SystemExit('Build the fixed loader first: python scripts/build_archive_bootloader.py')
        return str(target)
gamepad_datas=collect_data_files('vgamepad')
gamepad_binaries=collect_dynamic_libs('vgamepad')
if (project_root/'bin/HidHide').is_dir():
    gamepad_datas.append((str(project_root/'bin/HidHide'),'bin/HidHide'))
bridge_datas = []
python32_dir = project_root / 'bin' / 'python32'
if python32_dir.is_dir():
    bridge_datas.extend(bridge_files(python32_dir))

a = Analysis(
    ['main.py'],
    pathex=[str(project_root/'vendor')],
    binaries=[
        ('bin\\D3DCOMPILER_47.dll', '.'),
        ('bin\\cgfs16_overlay.dll', 'bin'),
        ('bin\\fifa16_narration.dll', 'bin'),
        ('bin\\server16_first_person_v14.dll', 'bin'),
        ('bin\\FifaLibrary16.dll',  'bin'),
        ('bin\\career_jobs_runtime.dll', 'bin'),
    ] + gamepad_binaries,
    datas=[
        ('server16_py\\assets\\startup_baseline.json', 'server16_py/assets'),
        ('server16_py\\assets\\flags', 'server16_py/assets/flags'),
        ('server16_py\\offsets.json', 'server16_py'),
        ('server16_py\\db_worker.py', 'server16_py'),
        ('server16_py\\career_save_worker.py', 'server16_py'),
        ('server16_py\\bh_worker.py', 'server16_py'),
        ('server16_py\\locales\\en.json', 'server16_py/locales'),
        ('server16_py\\locales\\pt.json', 'server16_py/locales'),
        ('server16_py\\locales\\es.json', 'server16_py/locales'),
        ('server16.ico', '.'),
    ] + bridge_datas + gamepad_datas,
    hiddenimports=['sqlite3','pygame','pygame._sdl2.controller','vgamepad',
        'clr',
        'rarfile',
        'numpy',
        'PIL.Image',
        'PIL.ImageDraw',
        'PIL.ImageFont',
        'PIL.DdsImagePlugin',
        'psutil',
        'server16_py.career_save_worker',
        'server16_py.career_read',
        'server16_py.career_active_save',
        'server16_py.career_context',
        'server16_py.fifa_db',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = ServerEXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Server16Python',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['server16.ico'],
)
