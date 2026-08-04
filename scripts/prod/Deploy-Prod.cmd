@echo off
rem deploy-prod.ps1 uses repo-relative paths (infra\*.bicep, .env.prod), so run it from the repo root.
pushd "%~dp0..\.."
pwsh -NoProfile -ExecutionPolicy Bypass -File "infra\deploy-prod.ps1" %*
set "exitCode=%errorlevel%"
popd
if not "%exitCode%"=="0" pause
exit /b %exitCode%
