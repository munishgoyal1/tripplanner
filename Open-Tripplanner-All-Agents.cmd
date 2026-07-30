@echo off
setlocal
where pwsh.exe >nul 2>&1
if %errorlevel%==0 (
  pwsh.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\open-agent-windows.ps1" -IncludeWorker2
) else (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\open-agent-windows.ps1" -IncludeWorker2
)
if errorlevel 1 pause
endlocal