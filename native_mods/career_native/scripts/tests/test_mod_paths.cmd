@echo off
setlocal
call "%~dp0..\env.cmd" "tests" "test_mod_paths"
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /W4 /WX /EHsc /MT "%CAREER_ROOT%\tests\core\test_mod_paths.cpp" /Fe:test_mod_paths.exe
if errorlevel 1 exit /b 1
test_mod_paths.exe
if errorlevel 1 exit /b 1
popd
endlocal
