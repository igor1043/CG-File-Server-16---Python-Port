@echo off
setlocal
call "%~dp0..\env.cmd" "tests" "test_keeper_auto_keys"
if errorlevel 1 exit /b 1
cl /nologo /std:c11 /W4 /WX /O2 /MT /D_CRT_SECURE_NO_WARNINGS /Fe:test_keeper_auto_keys.exe "%CAREER_ROOT%\tests\core\test_keeper_auto_keys.c"
if errorlevel 1 exit /b 1
test_keeper_auto_keys.exe
if errorlevel 1 exit /b 1
popd
endlocal
