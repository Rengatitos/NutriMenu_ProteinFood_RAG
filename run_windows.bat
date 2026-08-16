@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo No existe .venv. Ejecuta primero setup_windows.bat
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
python app.py
