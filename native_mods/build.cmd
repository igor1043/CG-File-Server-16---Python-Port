@echo off
setlocal
call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvarsall.bat" x64 >nul
if errorlevel 1 exit /b 1
pushd "%~dp0.."
if not exist build mkdir build
cl /nologo /std:c++17 /W4 /WX /O2 /MT /LD native_mods\mascot\mascot_goal_line.cpp /Fobuild\presentation_mascot.obj /Febuild\mascot_goal_line_v26.dll /link /NOLOGO /IMPLIB:build\presentation_mascot.lib
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /W4 /WX /O2 /MT /LD native_mods\pyro\stadium_pyrotechnics.cpp /Fobuild\presentation_pyro.obj /Febuild\stadium_pyrotechnics.dll /link /NOLOGO /IMPLIB:build\presentation_pyro.lib user32.lib
if errorlevel 1 exit /b 1
popd
endlocal
