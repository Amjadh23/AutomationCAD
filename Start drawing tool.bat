@echo off
cd /d "%~dp0"
title Bulkhead drawing tool
if not exist ".venv\Scripts\shipdraw.exe" (
  echo The drawing tool is not installed yet. See README.md, section "Setup".
  pause
  exit /b 1
)
".venv\Scripts\shipdraw.exe" serve
pause
