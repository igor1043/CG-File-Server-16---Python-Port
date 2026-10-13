@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" python -m venv --system-site-packages .venv
".venv\Scripts\python.exe" -m pip install sentence-transformers
pause
