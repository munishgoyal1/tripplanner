@echo off
setlocal
set "REPO_ROOT=%~dp0\..\.."
pwsh -NoProfile -ExecutionPolicy Bypass -File "%REPO_ROOT%\infra\migration\Invoke-OneClickMigration.ps1" -Operation Provision %*
exit /b %ERRORLEVEL%