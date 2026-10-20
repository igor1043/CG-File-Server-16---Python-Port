@echo off
setlocal
pushd "%~dp0.."
call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 exit /b 1
if not exist build\career_overlay mkdir build\career_overlay
cl /nologo /O2 /W3 /EHsc /std:c++17 tests\native_input_gate_test.cpp /Fo:build\career_overlay\ /Fe:build\career_overlay\native_input_gate_test.exe /link user32.lib gdi32.lib ole32.lib
if errorlevel 1 exit /b 1
build\career_overlay\native_input_gate_test.exe
if errorlevel 1 exit /b 1
build\career_overlay\native_input_gate_test.exe bootstrap
if errorlevel 1 exit /b 1
popd
endlocal
