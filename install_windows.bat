@echo off
setlocal
cd /d "%~dp0"

echo =============================================
echo Timur Translator Realtime V12 Interview Audio - Windows setup
echo =============================================
echo.

where py >nul 2>nul
if %errorlevel%==0 (
    echo Creating virtual environment...
    py -3.13 -m venv .venv >nul 2>nul
    if errorlevel 1 py -m venv .venv
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo ERROR: Python was not found.
        echo Install Python 3.13 x64 from python.org and enable "Add python.exe to PATH".
        pause
        exit /b 1
    )
    echo Creating virtual environment...
    python -m venv .venv
)

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Could not create .venv.
    pause
    exit /b 1
)

echo Updating pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :fail

echo Installing dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :fail

echo.
echo Setup complete. Run run_windows.bat
pause
exit /b 0

:fail
echo.
echo ERROR: Installation failed.
echo Python 3.13 x64 is recommended. Check your internet connection and try again.
pause
exit /b 1
