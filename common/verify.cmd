@echo off
setlocal
call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 exit /b 1
pushd "%~dp0"
if not exist build mkdir build
cl /nologo /std:c++17 /W4 /WX /O2 /MT test_scene_lua.cpp /Fobuild\ /Febuild\test_scene_lua.exe /link /NOLOGO
if errorlevel 1 exit /b 1
build\test_scene_lua.exe
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /W4 /WX /O2 /MT test_scene_startup.cpp /Fobuild\ /Febuild\test_scene_startup.exe /link /NOLOGO
if errorlevel 1 exit /b 1
build\test_scene_startup.exe
set result=%errorlevel%
popd
exit /b %result%
