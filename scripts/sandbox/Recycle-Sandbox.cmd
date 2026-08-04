@echo off
if "%~1"=="" (
  echo Usage: Recycle-Sandbox.cmd ^<new-slug^>            claim the parked sandbox
  echo        Recycle-Sandbox.cmd ^<slug^>                park that sandbox
  echo        Recycle-Sandbox.cmd ^<slug^> -As ^<new-slug^>  rename it directly
  exit /b 1
)
pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\dev\sandbox.ps1" -Recycle %*
set "exitCode=%errorlevel%"
if not "%exitCode%"=="0" pause
exit /b %exitCode%
