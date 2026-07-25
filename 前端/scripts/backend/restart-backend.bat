@echo off
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0restart-backend.ps1"
if errorlevel 1 (
  echo.
  echo Backend restart failed. Please keep this window open and send the error message to Codex.
  pause
)
