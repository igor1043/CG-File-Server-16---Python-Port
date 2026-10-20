@echo off
setlocal
call "%~dp0..\env.cmd" "tests" "test_career_transfer_cards"
if errorlevel 1 exit /b 1
cl /nologo /std:c11 /W4 /WX /O2 /MT /Fe:test_career_transfer_cards.exe "%CAREER_ROOT%\tests\providers\test_career_transfer_cards.c"
if errorlevel 1 exit /b 1
test_career_transfer_cards.exe
if errorlevel 1 exit /b 1
popd
endlocal
