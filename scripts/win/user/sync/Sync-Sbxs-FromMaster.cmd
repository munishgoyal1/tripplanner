@echo off
if "%~1"=="?" goto help
if /I "%~1"=="help" goto help
pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\..\..\dev\sync-sbxs-from-master.ps1" %*
set "exitCode=%errorlevel%"
if not "%exitCode%"=="0" pause
exit /b %exitCode%
:help
pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\..\..\dev\show-launcher-help.ps1" sync-sbxs-from-master