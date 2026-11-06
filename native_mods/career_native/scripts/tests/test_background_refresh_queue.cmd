@echo off
setlocal
call "%~dp0..\env.cmd" "tests" "test_background_refresh_queue"
if errorlevel 1 exit /b 1
cl /nologo /std:c11 /W4 /WX /O2 /MT /Fe:test_background_refresh_queue.exe "%CAREER_ROOT%\tests\providers\test_background_refresh_queue.c" /link kernel32.lib
if errorlevel 1 exit /b 1
test_background_refresh_queue.exe
if errorlevel 1 exit /b 1
popd
endlocal
