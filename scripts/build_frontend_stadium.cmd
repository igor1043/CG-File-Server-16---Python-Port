@echo off
setlocal
call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 exit /b 1
if not defined FRONTEND_STADIUM_OUTPUT set "FRONTEND_STADIUM_OUTPUT=%TEMP%\server16_frontend_stadium_build"
if not exist "%FRONTEND_STADIUM_OUTPUT%" mkdir "%FRONTEND_STADIUM_OUTPUT%"
pushd "%FRONTEND_STADIUM_OUTPUT%"
cl /nologo /O2 /W4 /WX /EHsc /std:c++17 /MT "%~dp0..\tests\native_frontend_background_test.cpp" /Fe:native_frontend_background_test.exe
if errorlevel 1 exit /b 1
native_frontend_background_test.exe
if errorlevel 1 exit /b 1
cl /nologo /O2 /W4 /WX /LD /EHsc /std:c++17 /MT "%~dp0..\native_mods\frontend_stadium\frontend_stadium.cpp" /Fe:frontend_stadium.dll /link /INCREMENTAL:NO
set result=%errorlevel%
popd
exit /b %result%
