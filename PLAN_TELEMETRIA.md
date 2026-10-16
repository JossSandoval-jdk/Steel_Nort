# PLAN — Telemetría Real-Time: Collector → Web SCADA (SteelNort)

> **Estado (2026-09/10): plan ejecutado.** El resultado actual difiere en
> nombres y prefijos de lo planeado aqui (era la versión v1): la API única es
> la **v2** (`app/v2/`, prefijo `/api/v2`, puerto 8200), el router de
> telemetría vive en `app/v2/routers/telemetria.py`, el push ya no usa el path
> `/telemetria/muestras` sino `POST /api/v2/telemetria/push`, y el detector
> maneja 54 features (no 16). Este documento se conserva como registro
> histórico del diseño original; la guía del estado actual es
> `docs/ARQUITECTURA.md`.

Objetivo: pasar a D:\SteelNort_web solo los archivos necesarios del proyecto
D:\Steel_Nort (workload-collector + modelo entrenado), adaptarlos y conectarlos
en vivo con la web. Todo queda interno en la web.

## INSTANCIAS
- Collector lee la instancia de negocio: localhost:1434 (DB SteelNort, cuenta con VIEW SERVER STATE, NADA de sa).
- Backend web escribe/lee su BD SCADA: localhost:1433 (Trusted_Connection, DB SteelNort).
- Escritorio JavaFX cerrado: NO afecta (el daemon lee DMVs directo). Si muere el daemon, el heartbeat de la web lo detecta y alerta.

## LOGS (ubicación)
- backend\logs\            → logs de ejecución (daemon.log, telemetria_api.log, detector.log), rotativos (RotatingFileHandler).
- Eventos en vivo (errorlog, sesiones, deadlocks, waits): viajan en la telemetría por SSE; NO se guarden como CSV.
  Solo se persisten cuando disparan una anomalía (Alertas + Causas_Raiz en BD SCADA 1433).
- training\captures\<run>\ → logs de las capturas on-demand de entrenamiento (metrics.log, events.log) dentro de su corrida.

## PASO 1 — COPIAS (solo lo necesario)

Origen (D:\Steel_Nort)                 -> Destino (D:\SteelNort_web\backend)
workload-collector\metrics_collector.py -> app\collector\metrics_collector.py   (importar tal cual: ~55 métricas/7s)
workload-collector\log_event_collector.py -> app\collector\log_event_collector.py (sesiones/eventos)
workload-collector\config.py            -> app\collector\config.py              (leer de .env, sin sa hardcodeado)
workload-collector\requirements.txt     -> fusionar en backend\requirements.txt
output\modelado\deteccion\modelo_isolation_forest.joblib -> app\ml\artifacts\
output\modelado\deteccion\scaler.joblib                 -> app\ml\artifacts\
output\modelado\correlacion\features_modelo.csv         -> app\ml\artifacts\  (orden de las 16 variables)
output\modelado\correlacion\reglas_umbrales.csv         -> app\ml\artifacts\  (umbrales del negocio)
data_preparation\ (7 scripts + config)  -> training\nucleo\data_preparation\
modeling\ (5 scripts + util + config)   -> training\nucleo\modeling\
run_pipeline.py                          -> training\nucleo\run_pipeline.py
modeling\requirements.txt                -> training\nucleo\requirements.txt
(Dataset original de referencia, 1 sola copia, opcional) -> training\datasets\  (baseline para drift)

NO se copian: run.py, api_workload.py, seed.py, simular_anomalias.py (siguen en D:\Steel_Nort
para capturas on-demand de entrenamiento). NO se acumulan CSVs diarios.

Carpetas nuevas a crear:
  backend\training\{nucleo, captures, datasets, models}
  backend\ml\artifacts\
  backend\logs\

## PASO 2 — NUEVOS ARCHIVOS (conexión con la web)

backend\app\collector\stream_daemon.py
  - Bucle infinito cada STREAM_INTERVAL (7s) reusando get_system_metrics/get_sql_server_metrics/get_business_locks.
  - Login JWT (usuario servicio) + auto-refresh antes de expirar (120 min).
  - POST /telemetria/muestras (authorization header). Sin CSRF (máquina a máquina).
  - Si falla el backend: spool local en training\captures\spool\ + reintento con backoff.
  - Log a backend\logs\daemon.log.

backend\app\routers\telemetria.py
  - POST /telemetria/muestras -> valida, inyecta a ring buffer + detector.
  - GET  /telemetria/live      -> SSE para el navegador (fetch con header Authorization).
  - GET  /telemetria/estado    -> heartbeat: última muestra por nodo + corte detectado.
  - Log de peticiones a backend\logs\telemetria_api.log.

backend\app\services\telemetria.py
  - Ring buffer multi-nodo en memoria (~220 muestras ≈ 25 min). Solo memoria (schema).

backend\app\services\anomalias.py
  - En anomalía persiste: Predicciones_ML + Alertas + Heatmap_Anomalias (BD SCADA 1433).

backend\app\ml\detector.py
  - Carga joblib + scaler + features_modelo.csv (orden de 16 variables).
  - Ventana móvil de 10 muestras por nodo (igual que el entrenamiento offline).
  - scaler.transform -> decision_function -> score; es_anomalia según umbral (prd_umbral).
  - Normalización relativa por corrida: SOLO para entreno offline; en streaming se usa el StandardScaler fijo.

backend\app\services\drift.py
  - Cada N minutos: distribución del ring buffer vs baseline de producción (KS/z-score) -> marca "reentrenar".
  - Reguarda: solo disparar captura si hay operación normal SIN anomalías superpuestas.

backend\training\orchestrator_retrain.py (auto-reentreno)
  - Dispara captura on-demand (rol de run.py) -> nucleo\data_preparation (00->06) -> nucleo\modeling (01->05)
  - Nueva versión -> training\models\vN\ -> Modelos_ML.mdl_act=1 (la anterior queda para rollback).
  - Recálculo de umbrales del negocio (cuantiles q01/q05/q10 sobre scores de producción): NO reentrena.
  - Cambio de umbral != reentrenar (separados).

backend\app\main.py: registrar router telemetria.
backend\.env: agregar STREAM_API_URL, ML_MODEL_PATH, ML_FEATURES_PATH, TELEMETRIA_INTERVAL, TELEMETRIA_VENTANA, SPOOL_DIR, LOG_DIR.
backend\requirements.txt: + joblib, scikit-learn, sse-starlette (o usar StreamingResponse manual).

## PASO 3 — FRONTEND
frontend\src\hooks\useTelemetria.js
  - Suscripción SSE por fetch (envía Authorization) + reconexión automática + estado conexión.
frontend\src\pages\Dashboard.jsx
  - Reemplazar mock: CPU/RAM (/metrics/sistema ya existe), gauges SQL Server, sesiones activas/inactivas, mapa de anomalías.

## FLUJO RESULTANTE
1. Daemon arranca -> login JWT -> muestrea cada 7s -> POST a la web.
2. Backend -> ring buffer -> detector (score + anomalía).
3. Solo anomalía -> persiste en BD SCADA + SSE -> dashboard en vivo.
4. Drift -> captura automática -> pipeline interno -> vN del modelo + umbral del negocio.
5. Dashboard heartbeat: "última muestra hace Xs", rojo si > 3x intervalo.

## ÓRDEN DE EJECUCIÓN
1. Crear carpetas training\{nucleo,captures,datasets,models}, ml\artifacts y logs.
2. Copiar archivos del Paso 1.
3. Escribir stream_daemon.py + endpoints telemetria + detector + anomalias (Paso 2).
4. Frontend en vivo (Paso 3).
5. Auto-adaptación: drift + orchestrator_retrain + umbral de negocio.
6. Producción: NSSM/Tarea Windows con reinicio, secretos en .env, cuenta DB solo VIEW SERVER STATE.

## RIESGOS CUBIERTOS
Polling 7s controlado | sin sa en flujo | token expira -> auto-refresh + spool | heartbeat anti-silencio |
auto-reentreno no hornea anomalías | modelos versionados con rollback | escritorio cerrado no corta nada.