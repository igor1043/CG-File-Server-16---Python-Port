@echo off
setlocal
call "%~dp0..\env.cmd" "tests" "test_career_job_offer"
if errorlevel 1 exit /b 1
cl /nologo /std:c11 /W4 /WX /O2 /MT /Fe:test_career_job_offer.exe "%CAREER_ROOT%\tests\providers\test_career_job_offer.c"
if errorlevel 1 exit /b 1
test_career_job_offer.exe
if errorlevel 1 exit /b 1
cl /nologo /std:c11 /W4 /WX /O2 /MT /Fe:test_career_job_delivery.exe "%CAREER_ROOT%\tests\providers\test_career_job_delivery.c"
if errorlevel 1 exit /b 1
test_career_job_delivery.exe
if errorlevel 1 exit /b 1
popd
endlocal
