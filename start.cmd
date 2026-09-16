@echo off
rem One-click launcher wrapper so the script can be double-clicked on Windows.
rem All arguments are forwarded to start.ps1 (e.g. start.cmd -Local).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
if errorlevel 1 pause
