@echo off
pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\dev\all-worktrees-sync.ps1" %*
exit /b %errorlevel%