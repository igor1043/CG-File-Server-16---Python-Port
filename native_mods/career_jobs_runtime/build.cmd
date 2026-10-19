@echo off
setlocal
set "JOBS_SOURCE=%~dp0"
pushd "%~dp0..\.."
call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 exit /b 1
if not exist build\career_jobs_runtime mkdir build\career_jobs_runtime
cl /nologo /std:c11 /O2 /W3 /MT /LD /D_CRT_SECURE_NO_WARNINGS "%JOBS_SOURCE%career_jobs_runtime.c" /Fo:build\career_jobs_runtime\ /Fe:build\career_jobs_runtime\career_jobs_runtime.dll /link kernel32.lib user32.lib psapi.lib
if errorlevel 1 exit /b 1
copy /y build\career_jobs_runtime\career_jobs_runtime.dll bin\career_jobs_runtime.dll >nul
if errorlevel 1 exit /b 1
popd
endlocal

