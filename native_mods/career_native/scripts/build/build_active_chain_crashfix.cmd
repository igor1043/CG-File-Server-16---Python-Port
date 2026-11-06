@echo off
setlocal
rem FIFA Friends V12 integration: original native features plus selected Swiss additions.
call "%~dp0..\env.cmd" "build" "build_active_chain_crashfix"
if errorlevel 1 exit /b 1
rc /nologo /I"%CAREER_ROOT%\resources" /fo dinput8_active_chain_resource.res "%CAREER_ROOT%\resources\dinput8_active_chain_resource.rc"
if errorlevel 1 exit /b 1
cl /nologo /std:c11 /W4 /WX /O2 /MT /D_CRT_SECURE_NO_WARNINGS /c "%CAREER_ROOT%\src\core\fce_contracts.c" "%CAREER_ROOT%\src\core\fce_model.c" "%CAREER_ROOT%\src\core\fce_runtime.c" "%CAREER_ROOT%\src\features\crowd\crowd_runtime.c" "%CAREER_ROOT%\src\features\retirement\retirement_engine.c"
if errorlevel 1 exit /b 1
cl /nologo /std:c11 /W3 /O2 /MT /D_CRT_SECURE_NO_WARNINGS /c "%CAREER_ROOT%\src\host\dinput8_wrapper.c"
if errorlevel 1 exit /b 1
cl /nologo /std:c11 /W4 /WX /O2 /MT /D_CRT_SECURE_NO_WARNINGS /c "%CAREER_ROOT%\src\platform\stadium_thumbnail.c"
if errorlevel 1 exit /b 1
cl /nologo /std:c11 /W4 /WX /O2 /MT /D_CRT_SECURE_NO_WARNINGS /c "%CAREER_ROOT%\src\host\swiss_delta.c" "%CAREER_ROOT%\src\host\league_query_batches.c" "%CAREER_ROOT%\src\host\tournament_list_compat.c"
if errorlevel 1 exit /b 1
link /nologo /DLL /MAP:dinput8.map /MAPINFO:EXPORTS /OUT:dinput8.dll /DEF:"%CAREER_ROOT%\src\host\dinput8_wrapper.def" dinput8_wrapper.obj stadium_thumbnail.obj swiss_delta.obj league_query_batches.obj tournament_list_compat.obj fce_contracts.obj fce_model.obj fce_runtime.obj crowd_runtime.obj retirement_engine.obj dinput8_active_chain_resource.res kernel32.lib user32.lib gdi32.lib psapi.lib bcrypt.lib ole32.lib windowscodecs.lib
if errorlevel 1 exit /b 1
copy /Y dinput8.dll "%REPO_ROOT%\dinput8.dll" >nul
if errorlevel 1 exit /b 1
popd
endlocal
