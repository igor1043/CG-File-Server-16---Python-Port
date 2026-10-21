# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


project_root = Path(SPECPATH)
bridge_datas = []
python32_dir = project_root / 'bin' / 'python32'
if python32_dir.is_dir():
    bridge_datas.append((str(python32_dir), 'bin/python32'))

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[
        ('bin\\D3DCOMPILER_47.dll', '.'),
        ('bin\\cgfs16_overlay.dll', 'bin'),
        ('bin\\cgfs16_inject.exe',  'bin'),
        ('bin\\fifa16_narration.dll', 'bin'),
        ('bin\\server16_first_person_v13.dll', 'bin'),
        ('bin\\FifaLibrary16.dll',  'bin'),
        ('bin\\career_jobs_runtime.dll', 'bin'),
    ],
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
    ] + bridge_datas,
    hiddenimports=[
        'clr',
        'rarfile',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
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
