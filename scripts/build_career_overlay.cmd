@echo off
setlocal
pushd "%~dp0.."
call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 exit /b 1
if not exist build\career_overlay mkdir build\career_overlay
cl /nologo /O2 /W3 /LD /EHsc /std:c++17 server16_py\d3d_overlay\cgfs16_overlay.cpp server16_py\d3d_overlay\stadium_selector_bridge.cpp server16_py\d3d_overlay\crowd_bridge.cpp server16_py\d3d_overlay\mod_xinput_gate.cpp server16_py\d3d_overlay\ranking_input_gate.cpp /Fo:build\career_overlay\ /Fe:build\career_overlay\cgfs16_overlay.dll /link d3d11.lib dxgi.lib d3dcompiler.lib user32.lib gdi32.lib ole32.lib
if errorlevel 1 exit /b 1
cl /nologo /O2 /W3 /EHsc /std:c++17 tests\native_selector_bridge_test.cpp server16_py\d3d_overlay\crowd_bridge.cpp server16_py\d3d_overlay\mod_xinput_gate.cpp server16_py\d3d_overlay\ranking_input_gate.cpp /Fo:build\career_overlay\ /Fe:build\career_overlay\native_selector_bridge_test.exe /link user32.lib gdi32.lib ole32.lib
if errorlevel 1 exit /b 1
build\career_overlay\native_selector_bridge_test.exe
if errorlevel 1 exit /b 1
popd
endlocal
