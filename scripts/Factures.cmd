@echo off
rem Factures.cmd - double-click launcher for Factures.ps1.
rem Copy this file to your desktop. It runs the script from the project folder below.
set "PROJECT_DIR=C:\DEV\Factures"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PROJECT_DIR%\scripts\Factures.ps1"
if errorlevel 1 pause
