@echo off
setlocal
set "repo_root=%~dp0..\..\..\.."
set "python_bin=%repo_root%\.venv\Scripts\python.exe"
if not exist "%python_bin%" set "python_bin=python"
"%python_bin%" -u "%repo_root%\scripts\dev\multiagent.py" quality-loop %*
