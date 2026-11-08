@echo off
setlocal
call "%~dp0..\env.cmd" "tests" "test_career_retirement_live"
if errorlevel 1 exit /b 1
cl /nologo /std:c11 /W4 /WX /O2 /MT /D_CRT_SECURE_NO_WARNINGS "%CAREER_ROOT%\tests\providers\test_career_retirement_live.c" /Fe:test_career_retirement_live.exe
if errorlevel 1 exit /b 1
test_career_retirement_live.exe
if errorlevel 1 exit /b 1
popd
endlocal
