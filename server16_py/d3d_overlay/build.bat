@echo off
setlocal
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
for /f "usebackq delims=" %%i in (`"%VSWHERE%" -latest -products * -property installationPath`) do set "VSINSTALL=%%i"
if not defined VSINSTALL exit /b 1
call "%VSINSTALL%\VC\Auxiliary\Build\vcvarsall.bat" x64 >nul 2>&1
if errorlevel 1 exit /b 1
set "SRCDIR=%~dp0"
set "OUTDIR=%~dp0..\..\runtime"
if not exist "%OUTDIR%" mkdir "%OUTDIR%"
pushd "%SRCDIR%"
cl /nologo /O2 /W3 /LD /EHsc /std:c++17 cgfs16_overlay.cpp stadium_selector_bridge.cpp crowd_bridge.cpp mod_xinput_gate.cpp ranking_input_gate.cpp ultrawide_bridge.cpp /Fe:"%OUTDIR%\cgfs16_overlay.dll" /Fd:"%OUTDIR%\cgfs16_overlay.pdb" /link d3d11.lib dxgi.lib d3dcompiler.lib user32.lib gdi32.lib ole32.lib
set "RESULT=%ERRORLEVEL%"
popd
exit /b %RESULT%
