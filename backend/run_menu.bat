@echo off
REM ============================================================
REM SteelNort - Menú Interactivo de Pipeline, Modelado y Experimentos
REM ------------------------------------------------------------
REM Permite ver paso a paso la preparación de datos, entrenamiento
REM de modelos, reglas expertas, comparación de algoritmos y métricas.
REM
REM Uso: doble clic o backend\run_menu.bat
REM ============================================================
cd /d "%~dp0"

set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] No se encontro el entorno virtual en .venv
  echo         Usando python del sistema...
  python "app\tools\menu_doc.py"
) else (
  ".venv\Scripts\python.exe" "app\tools\menu_doc.py"
)

if errorlevel 1 pause

