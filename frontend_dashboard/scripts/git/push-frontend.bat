@echo off
chcp 65001 >nul
powershell -ExecutionPolicy Bypass -File "%~dp0push-frontend.ps1"
pause
