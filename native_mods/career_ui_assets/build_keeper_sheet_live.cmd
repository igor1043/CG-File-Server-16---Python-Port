@echo off
setlocal
call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 exit /b 1
if not exist build mkdir build
cl /nologo /std:c11 /W4 /WX /O2 /MT /D_CRT_SECURE_NO_WARNINGS /LD career_keeper_sheet_live.c /Fobuild\ /Febuild\career_keeper_sheet_live.dll /link /NOLOGO /IMPLIB:build\career_keeper_sheet_live.lib
if errorlevel 1 exit /b 1
cl /nologo /std:c11 /W4 /WX /O2 /MT test_keeper_pitch_sheet.c /Fobuild\test_keeper_pitch_sheet.obj /Febuild\test_keeper_pitch_sheet.exe
if errorlevel 1 exit /b 1
build\test_keeper_pitch_sheet.exe
if errorlevel 1 exit /b 1
endlocal
