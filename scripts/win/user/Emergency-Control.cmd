@echo off
if "%~1"=="?" goto help
if /I "%~1"=="help" goto help
pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\..\dev\emergency-control.ps1" %*
exit /b %errorlevel%
:help
pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\..\dev\show-launcher-help.ps1" emergency-control
