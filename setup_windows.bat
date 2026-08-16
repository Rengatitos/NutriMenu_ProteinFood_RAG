@echo off
setlocal
cd /d "%~dp0"
python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if not exist .env copy .env.example .env
python scripts\bootstrap.py --pull
if errorlevel 1 (
  echo.
  echo Revisa que Ollama este instalado y ejecutandose.
  pause
  exit /b 1
)
echo.
echo Instalacion terminada. Ejecuta run_windows.bat
pause
