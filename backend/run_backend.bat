@echo off
REM ============================================================
REM SteelNort Backend — Script de arranque (Windows)
REM ------------------------------------------------------------
REM Ejecuta el backend FastAPI con uvicorn usando el entorno
REM virtual (Python 3.12) y desde el directorio del backend.
REM
REM Uso:
REM   .\run_backend.bat          -> levanta la API en :8089
REM   .\run_backend.bat dev      -> modo recarga (reload)
REM ============================================================
setlocal
cd /d "%~dp0"

REM Selecciona el interpretador del entorno virtual.
set PY=%~dp0.venv\Scripts\python.exe
if not exist "%PY%" (
    echo [ERROR] No se encontro el entorno virtual.
    echo Cree el venv primero:
    echo     py -3.12 -m venv .venv
    echo     .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

REM Modo por defecto (recarga opcional segun el argumento).
set FLAGS=--host 127.0.0.1 --port 8089
if /I "%~1"=="dev" set FLAGS=%FLAGS% --reload
if /I "%~1"=="test" (
    set DATABASE_URL=sqlite:///./steelnort_test.db
    echo [SteelNort] Modo pruebas: SQLite local (steelnort_test.db)
)

echo [SteelNort] Iniciando API en http://127.0.0.1:8089 ...
"%PY%" -m uvicorn app.main:app %FLAGS%