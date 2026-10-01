@echo off
setlocal EnableDelayedExpansion
REM =====================================================================
REM  entrenar_v3.bat  -  Reentrena el detector contra el baseline LIVE.
REM
REM  Uso:  entrenar_v3.bat [minutos] [saltar_armado] [saltar_pipeline]
REM          minutos         = duracion de la captura del baseline normal
REM                            en vivo (default 30; recomendado 20-60)
REM          saltar_armado   = 1 para NO re-capturar ni reconstruir el
REM                            dataset v3 (si ya lo corriste antes)
REM          saltar_pipeline = 1 para NO re-ejecutar 01-05 (si ya corrieron)
REM
REM  El daemon y el backend deben estar corriendo: la captura lee el
REM  estado LIVE que empuja el daemon al backend (127.0.0.1:8089).
REM =====================================================================

set "PYTHON=D:\SteelNort_web\backend\.venv\Scripts\python.exe"
set "BACK=D:\SteelNort_web\backend"
set "MIN=%1"
if "%MIN%"=="" set "MIN=30"
set "SALTAR_ARMADO=%2"
set "SALTAR_PIPELINE=%3"
if "%SALTAR_ARMADO%"=="" set "SALTAR_ARMADO=0"
if "%SALTAR_PIPELINE%"=="" set "SALTAR_PIPELINE=0"

set "STEELNORT_DATASET_SET=integrado_v3"
set "STEELNORT_MODELADO_SET=modelado_v3"
set "STEELNORT_CAPTURA_SALIDA=%BACK%\training\output\integrado_v3\captura_live.csv"

echo =====================================================================
echo  ENTRENAMIENTO V3  -  baseline live de %MIN% minutos
echo =====================================================================

if "%SALTAR_ARMADO%"=="1" goto :pip

echo.
echo [1/6] Capturando baseline normal en vivo (%MIN% min)...
"%PYTHON%" "%BACK%\training\capturar_live_v3.py" %MIN%
if errorlevel 1 goto :err

echo.
echo [2/6] Construyendo dataset v3 (v2 + captura live)...
"%PYTHON%" "%BACK%\training\construir_dataset_v3.py"
if errorlevel 1 goto :err

:pip
pushd "%BACK%\training\nucleo\modeling"

echo.
echo [3/6] Pipeline de modelado (01-05). Esto puede tomar varios minutos...
if "%SALTAR_PIPELINE%"=="1" goto :copod
"%PYTHON%" 01_muestras.py
if errorlevel 1 goto :pop_err
"%PYTHON%" 02_correlacion.py
if errorlevel 1 goto :pop_err
"%PYTHON%" 03_deteccion_isolation_forest.py
if errorlevel 1 goto :pop_err
"%PYTHON%" 04_reglas_motor.py
if errorlevel 1 goto :pop_err
"%PYTHON%" 05_diagnostico_resultados.py
if errorlevel 1 goto :pop_err

:copod
echo.
echo [4/6] Pineando features_modelo.csv y entrenando COPOD v3...
"%PYTHON%" "%BACK%\training\generar_copod_v3.py"
if errorlevel 1 goto :pop_err

popd

echo.
echo [5/6] Promoviendo artefactos v3 a ml/artifacts (respalda los v2)...
"%PYTHON%" "%BACK%\training\promover_v3.py"
if errorlevel 1 goto :err

echo.
echo [6/6] LISTO.
echo   * Reinicia el backend para cargar los artefactos v3:
echo       backend\run_backend.bat
echo   * El detector usara un baseline que incluye el api_status actual.
echo =====================================================================
goto :eof

:pop_err
popd
:err
echo.
echo [ERROR] El paso anterior fallo. Revisa el mensaje de arriba.
echo =====================================================================
goto :eof