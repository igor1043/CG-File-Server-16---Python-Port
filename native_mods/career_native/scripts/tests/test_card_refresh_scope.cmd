@echo off
setlocal
call "%~dp0..\env.cmd" "tests" "test_card_refresh_scope"
if errorlevel 1 exit /b 1
cl /nologo /std:c11 /W4 /WX /O2 /MT "%CAREER_ROOT%\tests\providers\test_card_refresh_scope.c" /Fe:test_card_refresh_scope.exe
if errorlevel 1 exit /b 1
test_card_refresh_scope.exe
if errorlevel 1 exit /b 1
popd
endlocal
