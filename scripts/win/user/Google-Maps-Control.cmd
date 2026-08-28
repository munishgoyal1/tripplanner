@echo off
pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\..\..\infra\gcp\set-google-maps-access.ps1" %*