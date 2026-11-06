@echo off
setlocal
call "%~dp0scripts\build\build_active_chain_crashfix.cmd"
if errorlevel 1 exit /b 1
call "%~dp0scripts\build\build_retirement_offline_worker.cmd"
if errorlevel 1 exit /b 1
echo Build concluido. DLL no Dev e workers em ModCarrerMode.
endlocal
