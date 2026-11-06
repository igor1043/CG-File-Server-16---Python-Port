@echo off
setlocal
call "%~dp0..\env.cmd" "tests" "test_market_save_state"
if errorlevel 1 exit /b 1
cl /nologo /std:c11 /W4 /WX /Od /MT /D_CRT_SECURE_NO_WARNINGS "%CAREER_ROOT%\tests\providers\test_market_save_state.c" /Fe:test_market_save_state.exe
if errorlevel 1 exit /b 1
test_market_save_state.exe
if errorlevel 1 exit /b 1
popd
endlocal
