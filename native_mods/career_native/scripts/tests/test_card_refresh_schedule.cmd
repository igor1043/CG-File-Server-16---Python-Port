@echo off
setlocal
call "%~dp0..\env.cmd" "tests" "test_card_refresh_schedule"
if errorlevel 1 exit /b 1
cl /nologo /std:c11 /W4 /WX /O2 /MT /D_CRT_SECURE_NO_WARNINGS /Fe:test_card_refresh_schedule.exe "%CAREER_ROOT%\tests\providers\test_card_refresh_schedule.c"
if errorlevel 1 exit /b 1
test_card_refresh_schedule.exe
if errorlevel 1 exit /b 1
popd
endlocal
