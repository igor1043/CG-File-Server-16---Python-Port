@echo off
setlocal
pushd "%~dp0.."
call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
if not "%ERRORLEVEL%"=="0" exit /b %ERRORLEVEL%
if not exist build mkdir build
cl /nologo /O2 /W4 /WX /EHsc /std:c++17 /MT tests\native_head_mesh_filter_test.cpp /Fo:build\native_head_mesh_filter_test.obj /Fe:build\native_head_mesh_filter_test.exe
if not "%ERRORLEVEL%"=="0" exit /b %ERRORLEVEL%
build\native_head_mesh_filter_test.exe
if not "%ERRORLEVEL%"=="0" exit /b %ERRORLEVEL%
cl /nologo /O2 /W4 /WX /EHsc /std:c++17 /MT tests\native_first_person_test.cpp /Fo:build\native_first_person_test.obj /Fe:build\native_first_person_test.exe
if not "%ERRORLEVEL%"=="0" exit /b %ERRORLEVEL%
build\native_first_person_test.exe
if not "%ERRORLEVEL%"=="0" exit /b %ERRORLEVEL%
cl /nologo /O2 /W4 /WX /LD /EHsc /std:c++17 /MT /DSERVER16_CAMERA_TEST native_mods\first_person\first_person.cpp /Fo:build\server16_first_person_test.obj /Fe:build\server16_first_person_test.dll /link /INCREMENTAL:NO user32.lib
if not "%ERRORLEVEL%"=="0" exit /b %ERRORLEVEL%
cl /nologo /O2 /W4 /WX /EHsc /std:c++17 /MT tests\native_camera_channel_test.cpp /Fo:build\native_camera_channel_test.obj /Fe:build\native_camera_channel_test.exe
if not "%ERRORLEVEL%"=="0" exit /b %ERRORLEVEL%
build\native_camera_channel_test.exe
if not "%ERRORLEVEL%"=="0" exit /b %ERRORLEVEL%
popd
endlocal
