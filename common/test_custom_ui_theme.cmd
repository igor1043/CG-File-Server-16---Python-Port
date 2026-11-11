@echo off
setlocal
if "%VS_VCVARS64%"=="" set "VS_VCVARS64=C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
call "%VS_VCVARS64%" >nul
if errorlevel 1 exit /b 1
set "THEME_SOURCE=%~dp0"
if "%~1"=="" (set "THEME_OUTPUT=%TEMP%\fifa16-ui-theme-tests") else (set "THEME_OUTPUT=%~f1")
if not exist "%THEME_OUTPUT%" mkdir "%THEME_OUTPUT%"
pushd "%THEME_OUTPUT%"
if errorlevel 1 exit /b 1
cl /nologo /O2 /W4 /EHsc /std:c++17 /MT "%THEME_SOURCE%test_custom_ui_theme.cpp" /Fe:test_custom_ui_theme.exe
if errorlevel 1 exit /b 1
test_custom_ui_theme.exe
if errorlevel 1 exit /b 1
popd
exit /b 0
