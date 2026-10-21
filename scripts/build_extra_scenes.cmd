@echo off
setlocal
call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 exit /b 1
if not defined EXTRA_SCENES_OUTPUT set "EXTRA_SCENES_OUTPUT=%TEMP%\server16_extra_scenes_build"
if not exist "%EXTRA_SCENES_OUTPUT%" mkdir "%EXTRA_SCENES_OUTPUT%"
pushd "%EXTRA_SCENES_OUTPUT%"
cl /nologo /O2 /W4 /WX /EHsc /std:c++17 /MT "%~dp0..\tests\native_extra_scenes_test.cpp" /Fe:native_extra_scenes_test.exe
if errorlevel 1 exit /b 1
native_extra_scenes_test.exe
if errorlevel 1 exit /b 1
cl /nologo /O2 /W4 /WX /LD /EHsc /std:c++17 /MT "%~dp0..\native_mods\extra_scenes\extra_scenes.cpp" /Fe:extra_scenes.dll /link /INCREMENTAL:NO user32.lib
set result=%errorlevel%
popd
exit /b %result%
