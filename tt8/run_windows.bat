@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Dependencies are not installed yet.
    echo Run install_windows.bat first.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" timur_translator.py
set EXITCODE=%errorlevel%
if not "%EXITCODE%"=="0" (
    echo.
    echo The application stopped with an error. Exit code: %EXITCODE%
    echo Open this debug log and send its last lines:
    echo %USERPROFILE%\.timur_translator_realtime\translator_debug.log
    echo.
    pause
)
exit /b %EXITCODE%
