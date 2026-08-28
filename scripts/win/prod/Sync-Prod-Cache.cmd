@echo off
pushd "%~dp0..\..\.."
pwsh -NoProfile -ExecutionPolicy Bypass -File "scripts\prod-cache-sync.ps1" %*
set "exitCode=%errorlevel%"
popd
if not "%exitCode%"=="0" pause
exit /b %exitCode%