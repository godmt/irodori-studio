@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0update-studio.ps1" %*
set "IRODORI_UPDATE_EXIT=%ERRORLEVEL%"
echo.
if not "%IRODORI_UPDATE_EXIT%"=="0" echo Update failed. Review the message above before closing this window.
if "%IRODORI_UPDATE_EXIT%"=="0" echo Update completed. You can now start Irodori Studio.
pause
exit /b %IRODORI_UPDATE_EXIT%
