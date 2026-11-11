@echo off
setlocal
call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 exit /b 1
if not defined GOAL_NEWS_OUTPUT set "GOAL_NEWS_OUTPUT=%TEMP%\fifa16_goal_news_build"
if not exist "%GOAL_NEWS_OUTPUT%" mkdir "%GOAL_NEWS_OUTPUT%"
pushd "%GOAL_NEWS_OUTPUT%"
cl /nologo /O2 /W4 /WX /EHsc /std:c++17 /MT "%~dp0..\tests\native_goal_news_test.cpp" /Fe:native_goal_news_test.exe
if errorlevel 1 exit /b 1
native_goal_news_test.exe
if errorlevel 1 exit /b 1
cl /nologo /O2 /W4 /WX /EHsc /std:c++17 /MT "%~dp0..\tests\native_goal_news_hooks_test.cpp" /Fe:native_goal_news_hooks_test.exe
if errorlevel 1 exit /b 1
native_goal_news_hooks_test.exe
if errorlevel 1 exit /b 1
cl /nologo /O2 /W4 /WX /LD /EHsc /std:c++17 /MT "%~dp0..\native_mods\goal_news\goal_news.cpp" /Fe:goal_news.dll /link /INCREMENTAL:NO
set result=%errorlevel%
popd
exit /b %result%
