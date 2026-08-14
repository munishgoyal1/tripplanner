@echo off
setlocal enabledelayedexpansion
rem Default is keep-alive: land the sandbox's work in the base branch, then
rem resync and keep the sandbox registered and active (sandbox.ps1 -Merge).
rem Pass -Discard to retire the sandbox after landing instead (sandbox.ps1 -Promote).
set "verb=-Merge"
set "args="
:parse
if "%~1"=="" goto :done
if /I "%~1"=="-Discard" (
  set "verb=-Promote"
) else if /I "%~1"=="--discard" (
  set "verb=-Promote"
) else (
  set "args=!args! "%~1""
)
shift
goto :parse
:done
pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\..\dev\sandbox.ps1" %verb% %args%
set "exitCode=%errorlevel%"
if not "%exitCode%"=="0" pause
exit /b %exitCode%
