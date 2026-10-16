@echo off
REM ============================================================
REM SteelNort - Arranque de la API v2 (backend)
REM ------------------------------------------------------------
REM Levanta FastAPI con el entorno virtual del backend en el
REM puerto 8200 (el mismo que esperan el proxy de Vite y el
REM servidor Express de frontend/server).
REM
REM Uso:  doble clic o  backend\run_backend.bat
REM ============================================================
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] No se encontro el entorno virtual en .venv
  echo         Cree el entorno e instale requirements.txt
  pause
  exit /b 1
)

".venv\Scripts\python.exe" -m uvicorn app.v2.main:app --host 127.0.0.1 --port 8200 --reload
