@echo off
setlocal
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
for /f "usebackq delims=" %%i in (`"%VSWHERE%" -latest -products * -property installationPath`) do set "VSINSTALL=%%i"
if not defined VSINSTALL exit /b 1
call "%VSINSTALL%\VC\Auxiliary\Build\vcvarsall.bat" x64 >nul 2>&1
if errorlevel 1 exit /b 1
pushd "%~dp0"
if not exist build mkdir build
cl /nologo /O2 /LD test_ultrawide_foreign.cpp /Fo:build\ /Fe:build\test_ultrawide_foreign.dll
if errorlevel 1 exit /b 1
cl /nologo /O2 /EHsc /std:c++17 /DULTRAWIDE_TEST test_ultrawide.cpp ultrawide_bridge.cpp /Fo:build\ /Fe:build\test_ultrawide.exe /link d3d11.lib dxgi.lib d3dcompiler.lib user32.lib shell32.lib
if errorlevel 1 exit /b 1
build\test_ultrawide.exe "..\..\..\data\ultrawide\st_bootflow_standard.dds" "..\..\..\data\ultrawide\st_bootflow_ultrawide.dds"
set "RESULT=%ERRORLEVEL%"
popd
exit /b %RESULT%
