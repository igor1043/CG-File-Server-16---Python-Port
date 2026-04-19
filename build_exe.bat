@echo off
setlocal
cd /d "%~dp0"

set "WORKPATH=build\pyinstaller"
set "DISTPATH=dist"

pyinstaller ^
  --noconfirm ^
  --clean ^
  --windowed ^
  --onefile ^
  --name Server16Python ^
  --distpath "%DISTPATH%" ^
  --workpath "%WORKPATH%" ^
  --add-data "server16_py\offsets.json;server16_py" ^
  main.py

echo.
echo Build finalizado.
echo EXE: %~dp0%DISTPATH%\Server16Python.exe
pause
