@echo off
setlocal
set "JOBS_SOURCE=%~dp0"
pushd "%~dp0..\.."
call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 exit /b 1
if not exist build\career_jobs_runtime mkdir build\career_jobs_runtime
cl /nologo /std:c11 /O2 /W3 /MT /D_CRT_SECURE_NO_WARNINGS "%JOBS_SOURCE%test_runtime.c" /Fo:build\career_jobs_runtime\ /Fe:build\career_jobs_runtime\test_runtime.exe /link kernel32.lib user32.lib psapi.lib
if errorlevel 1 exit /b 1
build\career_jobs_runtime\test_runtime.exe
if errorlevel 1 exit /b 1
popd
endlocal

