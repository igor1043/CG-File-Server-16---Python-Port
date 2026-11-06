@echo off
setlocal
call "%~dp0..\env.cmd" "tests" "build_retirement_engine_test"
if errorlevel 1 exit /b 1
cl /nologo /std:c11 /W4 /WX /O2 /MT /D_CRT_SECURE_NO_WARNINGS /I"%CAREER_ROOT%\src\features\retirement" "%CAREER_ROOT%\src\features\retirement\retirement_engine.c" "%CAREER_ROOT%\tests\core\retirement_engine_test.c" /Fe:retirement_engine_test.exe user32.lib gdi32.lib
if errorlevel 1 exit /b 1
if not "%~1"=="" retirement_engine_test.exe %*
if errorlevel 1 exit /b 1
popd
endlocal
