@echo off
setlocal
call "%~dp0..\env.cmd" "tests" "test_prepared_views"
if errorlevel 1 exit /b 1
cl /nologo /std:c11 /W4 /WX /O2 /MT /D_CRT_SECURE_NO_WARNINGS "%CAREER_ROOT%\tests\providers\test_prepared_views.c" /Fe:test_prepared_views.exe
if errorlevel 1 exit /b 1
test_prepared_views.exe
if errorlevel 1 exit /b 1
popd
endlocal
