@echo off
pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0merge-worktrees.ps1" %*
exit /b %errorlevel%
