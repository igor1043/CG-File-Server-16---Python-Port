@echo off
setlocal
call "%~dp0..\env.cmd" "tests" "test_derived_standings"
if errorlevel 1 exit /b 1
cl /nologo /std:c11 /W4 /WX /Od /MT /D_CRT_SECURE_NO_WARNINGS "%CAREER_ROOT%\tests\core\test_derived_standings.c" "%CAREER_ROOT%\src\core\fce_model.c" "%CAREER_ROOT%\src\core\fce_contracts.c" /Fe:test_derived_standings.exe
if errorlevel 1 exit /b 1
test_derived_standings.exe
if errorlevel 1 exit /b 1
popd
endlocal
