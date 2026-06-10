@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Dependencies are not installed yet.
    echo Run install_windows.bat first.
    pause
    exit /b 1
)

echo Running in debug mode. Keep this console open.
echo Log file: %USERPROFILE%\.timur_translator_realtime\translator_debug.log
echo.
".venv\Scripts\python.exe" timur_translator.py
set EXITCODE=%errorlevel%
echo.
echo Program exited with code %EXITCODE%.
echo Log file: %USERPROFILE%\.timur_translator_realtime\translator_debug.log
pause
exit /b %EXITCODE%
