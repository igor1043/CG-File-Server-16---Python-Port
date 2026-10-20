@echo off
setlocal
call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 exit /b 1
pushd "%~dp0"
if not exist build mkdir build
cl /nologo /std:c++17 /W4 /WX /O2 /MT timing_v14_test.cpp /Fobuild\ /Febuild\timing_v14_test.exe /link /NOLOGO
if errorlevel 1 exit /b 1
build\timing_v14_test.exe
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /W4 /WX /O2 /MT goal_v11_test.cpp /Fobuild\ /Febuild\goal_v11_test.exe /link /NOLOGO
if errorlevel 1 exit /b 1
build\goal_v11_test.exe
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /W4 /WX /O2 /MT lifecycle_v17_test.cpp /Fobuild\ /Febuild\lifecycle_v17_test.exe /link /NOLOGO
if errorlevel 1 exit /b 1
build\lifecycle_v17_test.exe
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /W4 /WX /O2 /MT ending_test.cpp /Fobuild\ /Febuild\ending_test.exe /link /NOLOGO
if errorlevel 1 exit /b 1
build\ending_test.exe
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /W4 /WX /O2 /MT teams_test.cpp /Fobuild\ /Febuild\teams_test.exe /link /NOLOGO
if errorlevel 1 exit /b 1
build\teams_test.exe
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /W4 /WX /O2 /MT palette_test.cpp /Fobuild\ /Febuild\palette_test.exe /link /NOLOGO
if errorlevel 1 exit /b 1
build\palette_test.exe
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /W4 /WX /O2 /MT presentation_test.cpp /Fobuild\ /Febuild\presentation_test.exe /link /NOLOGO
if errorlevel 1 exit /b 1
build\presentation_test.exe
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /W4 /WX /O2 /MT scene_clock_test.cpp /Fobuild\ /Febuild\scene_clock_test.exe /link /NOLOGO
if errorlevel 1 exit /b 1
build\scene_clock_test.exe
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /W4 /WX /O2 /MT runtime_scene_test.cpp /Fobuild\ /Febuild\runtime_scene_test.exe /link /NOLOGO user32.lib
if errorlevel 1 exit /b 1
build\runtime_scene_test.exe
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /W4 /WX /O2 /MT /LD stadium_pyrotechnics.cpp /Fobuild\ /Febuild\stadium_pyrotechnics.dll /link /NOLOGO user32.lib
set result=%errorlevel%
popd
exit /b %result%
