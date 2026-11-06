@echo off
setlocal
call "%~dp0..\env.cmd" "tests" "test_career_bank_mail"
if errorlevel 1 exit /b 1
cl /nologo /std:c11 /W3 /O2 /MT /Fe:test_career_bank_mail.exe "%CAREER_ROOT%\tests\providers\test_career_bank_mail.c" "%CAREER_ROOT%\src\core\fce_contracts.c" "%CAREER_ROOT%\src\core\fce_model.c" /link kernel32.lib
if errorlevel 1 exit /b 1
test_career_bank_mail.exe
if errorlevel 1 exit /b 1
popd
endlocal
