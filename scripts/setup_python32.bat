@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0.."

set "PYTHON32_DIR=bin\python32"
set "PYTHON_VER=3.9.13"
set "PYTHON_URL=https://www.python.org/ftp/python/%PYTHON_VER%/python-%PYTHON_VER%-embed-win32.zip"
set "PIP_URL=https://bootstrap.pypa.io/pip/3.9/get-pip.py"
set "PYTHONNET_VER=3.0.5"

if exist "%PYTHON32_DIR%\python.exe" if exist "%PYTHON32_DIR%\Lib\site-packages\pythonnet\__init__.py" if exist "%PYTHON32_DIR%\Lib\site-packages\_cffi_backend*.pyd" (
    echo [OK] 32-bit Python already at %PYTHON32_DIR%
    exit /b 0
)

echo [1/4] Downloading Python %PYTHON_VER% x86 embeddable...
if not exist "%PYTHON32_DIR%" mkdir "%PYTHON32_DIR%"
powershell -NoProfile -Command "Invoke-WebRequest -Uri '%PYTHON_URL%' -OutFile '%PYTHON32_DIR%\embed.zip' -UseBasicParsing"
if errorlevel 1 goto :failed

echo [2/4] Extracting...
powershell -NoProfile -Command "Expand-Archive -Path '%PYTHON32_DIR%\embed.zip' -DestinationPath '%PYTHON32_DIR%' -Force"
if errorlevel 1 goto :failed
del "%PYTHON32_DIR%\embed.zip" 2>nul
powershell -NoProfile -Command "$f = Get-Item '%PYTHON32_DIR%\python*._pth'; $c = (Get-Content $f.FullName) -replace '#import site','import site'; Set-Content $f.FullName $c"
if errorlevel 1 goto :failed

echo [3/4] Installing pip...
powershell -NoProfile -Command "Invoke-WebRequest -Uri '%PIP_URL%' -OutFile '%PYTHON32_DIR%\get-pip.py' -UseBasicParsing"
if errorlevel 1 goto :failed
"%PYTHON32_DIR%\python.exe" "%PYTHON32_DIR%\get-pip.py" --quiet
if errorlevel 1 goto :failed
del "%PYTHON32_DIR%\get-pip.py" 2>nul

echo [4/4] Installing pythonnet %PYTHONNET_VER%...
if not exist "%PYTHON32_DIR%\Lib\site-packages" mkdir "%PYTHON32_DIR%\Lib\site-packages"
"%PYTHON32_DIR%\python.exe" -m pip install "pythonnet==%PYTHONNET_VER%" --target "%PYTHON32_DIR%\Lib\site-packages" --upgrade --quiet
if errorlevel 1 goto :failed

echo [OK] 32-bit Python ready at %PYTHON32_DIR%
exit /b 0

:failed
echo [ERROR] Could not prepare 32-bit Python. See the command output above.
exit /b 1
