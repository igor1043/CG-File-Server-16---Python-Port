@echo off
setlocal
call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 exit /b 1
pushd "%~dp0"
if not exist build mkdir build
cl /nologo /std:c11 /W4 /WX /O2 /MT /D_CRT_SECURE_NO_WARNINGS /LD career_ui_assets.c /Fobuild\career_ui_assets.obj /Febuild\career_ui_assets.dll /link /NOLOGO /IMPLIB:build\career_ui_assets.lib
if errorlevel 1 exit /b 1
cl /nologo /std:c11 /W4 /WX /O2 /MT /D_CRT_SECURE_NO_WARNINGS test_ui_assets.c /Fobuild\test_ui_assets.obj /Febuild\test_ui_assets.exe
if errorlevel 1 exit /b 1
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Prepare-TestFixture.ps1"
if errorlevel 1 exit /b 1
build\test_ui_assets.exe "%~dp0build\fixture"
if errorlevel 1 exit /b 1
cl /nologo /std:c11 /W4 /WX /O2 /MT test_keeper_pitch_sheet.c /Fobuild\test_keeper_pitch_sheet.obj /Febuild\test_keeper_pitch_sheet.exe
if errorlevel 1 exit /b 1
build\test_keeper_pitch_sheet.exe
if errorlevel 1 exit /b 1
cl /nologo /std:c11 /W4 /WX /O2 /MT test_keeper_squad.c /Fobuild\test_keeper_squad.obj /Febuild\test_keeper_squad.exe
if errorlevel 1 exit /b 1
build\test_keeper_squad.exe
if errorlevel 1 exit /b 1
popd
endlocal
