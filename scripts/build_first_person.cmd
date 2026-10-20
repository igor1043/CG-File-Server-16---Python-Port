@echo off
setlocal
pushd "%~dp0.."
call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 exit /b 1
if not exist build mkdir build
cl /nologo /O2 /W4 /WX /LD /EHsc /std:c++17 /MT native_mods\first_person\first_person.cpp /Fo:build\server16_first_person.obj /Fe:bin\server16_first_person_v11.dll /link /INCREMENTAL:NO user32.lib
if errorlevel 1 exit /b 1
popd
endlocal
