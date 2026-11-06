@echo off
setlocal
call "%~dp0..\env.cmd" "tests" "test_stadium_thumbnail"
if errorlevel 1 exit /b 1
cl /nologo /std:c11 /W4 /WX /O2 /MT /D_CRT_SECURE_NO_WARNINGS /Fe:test_stadium_thumbnail.exe "%CAREER_ROOT%\tests\providers\test_stadium_thumbnail.c" "%CAREER_ROOT%\src\platform\stadium_thumbnail.c" /link ole32.lib windowscodecs.lib
if errorlevel 1 exit /b 1
test_stadium_thumbnail.exe
if errorlevel 1 exit /b 1
popd
endlocal
