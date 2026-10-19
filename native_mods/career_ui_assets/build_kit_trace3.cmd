@echo off
setlocal
call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 exit /b 1
if not exist build mkdir build
cl /nologo /std:c11 /W4 /WX /O2 /MT /D_CRT_SECURE_NO_WARNINGS /LD career_kit_trace3.c /Fobuild\ /Febuild\career_kit_trace3.dll /link /NOLOGO /IMPLIB:build\career_kit_trace3.lib
if errorlevel 1 exit /b 1
endlocal
