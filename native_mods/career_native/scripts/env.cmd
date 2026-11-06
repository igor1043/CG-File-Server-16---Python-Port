@echo off
rem Shared environment. Called inside the caller's SETLOCAL.
for %%I in ("%~dp0..") do set "CAREER_ROOT=%%~fI"
for %%I in ("%CAREER_ROOT%\..\..") do set "MOD_ROOT=%%~fI"
for %%I in ("%MOD_ROOT%\..") do set "REPO_ROOT=%%~fI"
if not defined VSCMD_ARG_TGT_ARCH call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 exit /b 1
if "%~2"=="build_active_chain_crashfix" (
    set "CAREER_WORK=%CAREER_ROOT%\build\production"
) else if "%~1"=="build" (
    set "CAREER_WORK=%CAREER_ROOT%\build\workers\%~2"
) else (
    set "CAREER_WORK=%CAREER_ROOT%\build\%~1\%~2"
)
if not exist "%CAREER_WORK%" mkdir "%CAREER_WORK%"
if not exist "%CAREER_WORK%" exit /b 1
if not "%~2"=="build_active_chain_crashfix" if exist "%CAREER_ROOT%\build\production\*.obj" copy /Y "%CAREER_ROOT%\build\production\*.obj" "%CAREER_WORK%\" >nul
pushd "%CAREER_WORK%"
if errorlevel 1 exit /b 1
if "%~2"=="test_ranking_card_action" if not exist ranking_card_tests mkdir ranking_card_tests
exit /b 0
