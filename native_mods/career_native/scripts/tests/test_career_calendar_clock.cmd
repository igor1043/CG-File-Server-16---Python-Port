@echo off
setlocal
call "%~dp0..\env.cmd" "tests" "test_career_calendar_clock"
if errorlevel 1 exit /b 1
cl /nologo /std:c11 /W4 /WX /Od /MT /D_CRT_SECURE_NO_WARNINGS "%CAREER_ROOT%\tests\providers\test_career_calendar_clock.c" "%CAREER_ROOT%\src\core\fce_model.c" "%CAREER_ROOT%\src\core\fce_contracts.c" /Fe:test_career_calendar_clock.exe
if errorlevel 1 exit /b 1
test_career_calendar_clock.exe
if errorlevel 1 exit /b 1
popd
endlocal
