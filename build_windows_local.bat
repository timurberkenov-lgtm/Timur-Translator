@echo off
setlocal
cd /d "%~dp0"

echo ================================================
echo Timur Translator Realtime - Windows EXE builder
echo ================================================
echo.

where py >nul 2>nul
if %errorlevel%==0 (
  py -3.13 -m venv .buildvenv >nul 2>nul
  if errorlevel 1 py -m venv .buildvenv
) else (
  python -m venv .buildvenv
)
if errorlevel 1 goto :fail

".buildvenv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :fail
".buildvenv\Scripts\python.exe" -m pip install -r windows\requirements.txt pyinstaller
if errorlevel 1 goto :fail

".buildvenv\Scripts\python.exe" -m py_compile windows\timur_translator.py
if errorlevel 1 goto :fail
".buildvenv\Scripts\python.exe" tests\verify_source.py windows
if errorlevel 1 goto :fail

rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
rmdir /s /q release 2>nul
mkdir release

".buildvenv\Scripts\python.exe" -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --windowed ^
  --name "Timur Translator Realtime" ^
  --icon "assets\TimurTranslator.ico" ^
  --hidden-import websocket ^
  --hidden-import pyaudio ^
  --collect-submodules websocket ^
  --collect-all soundcard ^
  windows\timur_translator.py
if errorlevel 1 goto :fail

copy /Y "dist\Timur Translator Realtime.exe" "release\Timur-Translator-Realtime-Windows-x64.exe" >nul
copy /Y "windows\README_WINDOWS.txt" "release\README_WINDOWS.txt" >nul
powershell -NoProfile -Command "Compress-Archive -Path 'release\*' -DestinationPath 'Timur-Translator-Realtime-Windows-x64.zip' -Force"

echo.
echo READY:
echo   %CD%\release\Timur-Translator-Realtime-Windows-x64.exe
echo   %CD%\Timur-Translator-Realtime-Windows-x64.zip
echo.
pause
exit /b 0

:fail
echo.
echo BUILD FAILED. Read the error above.
pause
exit /b 1
