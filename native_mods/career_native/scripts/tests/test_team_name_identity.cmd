@echo off
setlocal
call "%~dp0..\env.cmd" "tests" "test_team_name_identity"
if not "%errorlevel%"=="0" exit /b %errorlevel%
cl /nologo /std:c11 /W3 /O2 /MT /D_CRT_SECURE_NO_WARNINGS /Fe:test_team_name_identity.exe "%CAREER_ROOT%\tests\providers\test_team_name_identity.c" "%CAREER_ROOT%\src\platform\stadium_thumbnail.c" "%CAREER_ROOT%\src\host\swiss_delta.c" "%CAREER_ROOT%\src\host\league_query_batches.c" "%CAREER_ROOT%\src\host\tournament_list_compat.c" "%CAREER_ROOT%\src\core\fce_contracts.c" "%CAREER_ROOT%\src\core\fce_model.c" "%CAREER_ROOT%\src\core\fce_runtime.c" "%CAREER_ROOT%\src\features\crowd\crowd_runtime.c" "%CAREER_ROOT%\src\features\retirement\retirement_engine.c" /link kernel32.lib user32.lib gdi32.lib psapi.lib bcrypt.lib ole32.lib windowscodecs.lib
if not "%errorlevel%"=="0" exit /b %errorlevel%
test_team_name_identity.exe
if not "%errorlevel%"=="0" exit /b %errorlevel%
popd
endlocal
