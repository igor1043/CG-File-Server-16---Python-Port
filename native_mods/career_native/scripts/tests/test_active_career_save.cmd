@echo off
setlocal
call "%~dp0..\env.cmd" "tests" "test_active_career_save"
if errorlevel 1 exit /b 1
cl /nologo /std:c11 /W3 /O2 /MT /D_CRT_SECURE_NO_WARNINGS /Fe:test_active_career_save.exe "%CAREER_ROOT%\tests\providers\test_active_career_save.c" stadium_thumbnail.obj swiss_delta.obj league_query_batches.obj tournament_list_compat.obj fce_contracts.obj fce_model.obj fce_runtime.obj crowd_runtime.obj retirement_engine.obj /link kernel32.lib user32.lib gdi32.lib psapi.lib bcrypt.lib ole32.lib windowscodecs.lib
if errorlevel 1 exit /b 1
test_active_career_save.exe
if errorlevel 1 exit /b 1
popd
endlocal
