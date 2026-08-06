@echo off
setlocal
cd /d "%~dp0"
where pwsh.exe >nul 2>&1
if %errorlevel%==0 (
  pwsh.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup-dev-machine.ps1" -FullAgentEnvironment -IncludeMobile -OpenAgentWindows
) else (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup-dev-machine.ps1" -FullAgentEnvironment -IncludeMobile -OpenAgentWindows
)
if errorlevel 1 pause
endlocal