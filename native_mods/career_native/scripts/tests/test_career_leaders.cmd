@echo off
setlocal
call "%~dp0..\env.cmd" "tests" "test_career_leaders"
if errorlevel 1 exit /b 1
cl /nologo /std:c11 /W4 /WX /O2 /MT /D_CRT_SECURE_NO_WARNINGS /Fe:test_native_career_leaders.exe "%CAREER_ROOT%\tests\core\test_native_career_leaders.c" "%CAREER_ROOT%\src\core\fce_model.c" "%CAREER_ROOT%\src\core\fce_contracts.c"
if errorlevel 1 exit /b 1
test_native_career_leaders.exe
if errorlevel 1 exit /b 1
popd
endlocal
