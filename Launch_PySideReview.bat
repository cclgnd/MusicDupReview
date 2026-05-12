@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" "-m" "pyside_app.main"
) else (
  start "" "pythonw.exe" "-m" "pyside_app.main"
)
