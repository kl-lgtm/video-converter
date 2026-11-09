@echo off
cd /d "%~dp0"
if not exist ".venv312\Scripts\pythonw.exe" (
  echo Python environment not found. Run setup.ps1 first.
  pause
  exit /b 1
)
start "" ".venv312\Scripts\pythonw.exe" "main.py"
