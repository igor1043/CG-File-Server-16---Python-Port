@echo off
setlocal
call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 exit /b 1
if not defined PANORAMA_DRONE_OUTPUT set "PANORAMA_DRONE_OUTPUT=%TEMP%\server16_panorama_drone_build"
if not exist "%PANORAMA_DRONE_OUTPUT%" mkdir "%PANORAMA_DRONE_OUTPUT%"
pushd "%PANORAMA_DRONE_OUTPUT%"
cl /nologo /O2 /W4 /WX /EHsc /std:c++17 /MT "%~dp0..\tests\native_panorama_drone_test.cpp" /Fe:native_panorama_drone_test.exe
if errorlevel 1 exit /b 1
native_panorama_drone_test.exe
if errorlevel 1 exit /b 1
cl /nologo /O2 /W4 /WX /LD /EHsc /std:c++17 /MT "%~dp0..\native_mods\panorama_drone\panorama_drone.cpp" /Fe:panorama_drone_v3_1.dll /link /INCREMENTAL:NO
set result=%errorlevel%
popd
exit /b %result%
