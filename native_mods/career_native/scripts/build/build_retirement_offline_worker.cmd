@echo off
setlocal
call "%~dp0..\env.cmd" "build" "build_retirement_offline_worker"
if errorlevel 1 exit /b 1
cl /nologo /std:c11 /W4 /WX /O2 /MT /D_CRT_SECURE_NO_WARNINGS /I"%CAREER_ROOT%\src\features\retirement" "%CAREER_ROOT%\src\features\retirement\retirement_engine.c" "%CAREER_ROOT%\workers\retirement_offline_worker.c" /Fe:retirement_offline_worker.exe user32.lib gdi32.lib
if errorlevel 1 exit /b 1
copy /Y retirement_offline_worker.exe "%MOD_ROOT%\retirement_offline_worker.exe" >nul
if errorlevel 1 exit /b 1
popd
endlocal
