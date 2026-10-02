@echo off
REM ============================================================
REM SteelNort Backend v2 â€” Script de arranque (Windows)
REM ------------------------------------------------------------
REM Levanta la API v2 (app.v2.main:app) con uvicorn usando el
REM entorno virtual (Python 3.12) y desde el directorio del backend.
REM
REM Esta es la app que consume el frontend: monta sus routers bajo
REM el prefijo /api/v2. La v1 (app.main:app) NO se usa mas.
REM
REM Uso:
REM   .\run_backend.bat          -> levanta la API v2 en :8200
REM   .\run_backend.bat dev      -> modo recarga (reload)
REM
REM Los triggers, los heatmap y los datos viven en bdSteelNort_v2:
REM si se arranca sin base, la v2 lo avisa en el log y el esquema
REM queda incompleto. Ver database\instalar_disparadores.sql.
REM ============================================================
setlocal
cd /d "%~dp0"

REM Selecciona el interpretador del entorno virtual.
set PY=%~dp0.venv\Scripts\python.exe
if not exist "%PY%" (
    echo [ERROR] No se encontro el entorno virtual.
    echo Cree el venv primero:
    echo     py -3.12 -m venv .venv
    echo     .\.venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

REM Modo por defecto (recarga opcional segun el argumento).
set FLAGS=--host 127.0.0.1 --port 8200
if /I "%~1"=="dev" set FLAGS=%FLAGS% --reload

echo [SteelNort] Iniciando API v2 en http://127.0.0.1:8200/api/v2 ...
"%PY%" -m uvicorn app.v2.main:app %FLAGS%