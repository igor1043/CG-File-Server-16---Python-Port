@echo off
setlocal
if not "%~1"=="" (
    if not exist "%~dp0scripts\tests\%~1.cmd" exit /b 2
    call "%~dp0scripts\tests\%~1.cmd" %2 %3 %4 %5 %6 %7 %8 %9
    exit /b
)
for %%T in ("%~dp0scripts\tests\test_*.cmd") do (
    call "%%~fT"
    if errorlevel 1 exit /b 1
)
echo Testes compartilhados da V12 concluidos.
endlocal
