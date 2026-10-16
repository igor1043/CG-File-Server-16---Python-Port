from pathlib import Path
import subprocess,shutil,datetime,json,hashlib
source=Path(r'U:\fifa 16\ModCarrerMode\source\career_ui_assets');game=Path(r'U:\fifa 16')
fixture=source/'build/fixture/data/ui/imgAssets/careerCompetitionIcons';fixture.mkdir(parents=True,exist_ok=True)
for name in ('c1693.dds','c820.dds'):shutil.copy2(game/'data/ui/imgAssets/careerCompetitionIcons/c1693.dds',fixture/name)
(fixture/'c1700.dds').write_text('invalid DDS',encoding='utf8')
(fixture/'index.tsv').write_text('1693\t0\n820\t1\n',encoding='utf8')
script=source/'build_crash_fix.cmd'
script.write_text('@echo off\ncall "C:\\Program Files (x86)\\Microsoft Visual Studio\\18\\BuildTools\\VC\\Auxiliary\\Build\\vcvars64.bat" >nul\nif errorlevel 1 exit /b 1\ncl /nologo /std:c11 /W4 /WX /O2 /MT /D_CRT_SECURE_NO_WARNINGS /LD career_ui_assets.c /Fobuild\\career_ui_assets.obj /Febuild\\career_ui_assets.dll /link /NOLOGO /IMPLIB:build\\career_ui_assets.lib\nif errorlevel 1 exit /b 1\ncl /nologo /std:c11 /W4 /WX /O2 /MT /D_CRT_SECURE_NO_WARNINGS test_ui_assets.c /Fobuild\\test_ui_assets.obj /Febuild\\test_ui_assets.exe\nif errorlevel 1 exit /b 1\nbuild\\test_ui_assets.exe build\\fixture\n',encoding='utf8')
result=subprocess.run(['cmd.exe','/c','build_crash_fix.cmd'],cwd=source,capture_output=True)
print(result.stdout.decode(errors='replace'),flush=True)
if result.returncode:raise RuntimeError(result.stderr.decode(errors='replace'))
dest=game/'ModCarrerMode/mods/career_ui_assets/career_ui_assets.dll';backup=game/'runtime/crash_investigation'/('locale_fix_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S'));backup.mkdir(parents=True)
shutil.copy2(dest,backup/dest.name)
shutil.copy2(source/'build/career_ui_assets.dll',dest)
print(json.dumps(dict(deployed=str(dest),backup=str(backup),sha256=hashlib.sha256(dest.read_bytes()).hexdigest())),flush=True)
