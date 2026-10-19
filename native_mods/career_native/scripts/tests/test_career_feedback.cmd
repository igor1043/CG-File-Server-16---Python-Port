@echo off
setlocal
call "%~dp0..\env.cmd" "tests" "test_career_feedback"
if errorlevel 1 exit /b 1
cl /nologo /std:c11 /W4 /WX /O2 /MT /D_CRT_SECURE_NO_WARNINGS /Fe:test_career_feedback.exe "%CAREER_ROOT%\tests\providers\test_career_feedback.c" user32.lib gdi32.lib
if errorlevel 1 exit /b 1
test_career_feedback.exe
if errorlevel 1 exit /b 1
popd
endlocal
