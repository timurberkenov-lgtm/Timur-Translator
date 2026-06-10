@echo off
setlocal
set CONFIG=%USERPROFILE%\.timur_translator_realtime\config.json
if exist "%CONFIG%" (
    del /q "%CONFIG%"
    echo Saved translator settings removed.
) else (
    echo No saved translator settings were found.
)
pause
