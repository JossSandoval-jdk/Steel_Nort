# SteelNort — Arquitectura y Guía de Navegación

Índice de referencia para recorrer el repositorio. Describe el estado actual
(tras la organización de la rama `limpieza/organizacion`); la historia de cómo
se llegó aquí está en los commits de esa rama y en `ERRORES_ENCONTRADOS.md`.

## Mapa del repositorio

```
SteelNort_web/
├── backend/                  # Python 3.12 + FastAPI (la API vive en app/v2)
│   ├── app/
│   │   ├── v2/               # API v2: UNICA app expuesta
│   │   │   ├── main.py       #   arranque + lifespan (esquema, semilla, detector)
│   │   │   ├── routers/      #   auth, acceso, nodos, modelo, deteccion, datos,
│   │   │   │                 #   sistema, estado, telemetria (prefijo /api/v2)
│   │   │   ├── services/     #   logica de negocio (semilla, telemetria, anomalias...)
│   │   │   ├── models/       #   ORM SQLAlchemy (21 tablas canonicas)
│   │   │   ├── schemas/      #   DTOs Pydantic
│   │   │   ├── database.py   #   engine + init_db + verificar_esquema
│   │   │   └── config.py     #   settings tipados (.env)
│   │   ├── collector/        # telemetria: metrics_collector, log_event_collector,
│   │   │                     # xe_collector, stream_daemon (push al backend)
│   │   ├── ml/               # deteccion online: detector, decisor, ensamble_z
│   │   ├── security.py       # bcrypt, JWT, CSRF
│   │   └── config.py         # config del collector (STREAM_API_URL, credenciales)
│   ├── training/             # pipeline CRISP-DM
│   │   ├── nucleo/
│   │   │   ├── data_preparation/   # 00_inventario → 04_integracion + config
│   │   │   ├── modeling/           # 01_muestras → 05_diagnostico + config
│   │   │   │   └── experimental/   # experimentos (validar_candidato, etc.)
│   │   ├── captures/         # corridas on-demand + spool/ del daemon
│   │   ├── datasets/         # dataset runtime (dataset_muestras_train.pkl)
│   │   ├── output/           # inventario, limpio, integrado, modelado,
│   │   │                     # baseline, anomalias (nombres canonicos)
│   │   ├── capturar_live.py  # captura baseline normal desde la API v2
│   │   ├── construir_dataset.py  # base + captura → integrado/dataset_reentreno.csv
│   │   ├── generar_copod.py  # entrena COPOD y pinea features_modelo.csv
│   │   ├── promover.py       # modelado/ → ml/artifacts + training/datasets
│   │   ├── reentrenar_capturas.py  # reentreno periodico con capturas anomales
│   │   └── entrenar.bat      # orquesta captura → dataset → pipeline → promover
│   ├── ml/artifacts/         # artefactos DESPLEGADOS (modelo, scaler, features, reglas)
│   ├── tools/                # menu_pipeline, menu_laboratorio, generar_carga,
│   │                         # inyectar_anomalias, limpieza
│   ├── tests/                # pytest (test_validacion, test_decisor,
│   │                         # test_detector_zonal, simular_telemetria, probar_seguridad)
│   ├── run_backend.bat       # levanta la API v2 en 127.0.0.1:8200
│   └── crear_admin_v2.py     # crea el usuario administrador (una sola vez)
├── frontend/                 # React 19 + Vite + Express proxy + Socket.IO
│   └── server/               # proxy Node (server.js) → backend :8200/api/v2
├── database/                 # schema.sql, diccionario_datos.sql, instalar_disparadores.sql
├── docs/                     # FUNCIONALIDADES_PRINCIPALES.md, ARQUITECTURA.md (este)
├── README.md                 # vision general del proyecto
├── PLAN_TELEMETRIA.md        # plan original de la telemetria (historico)
└── ERRORES_ENCONTRADOS.md    # diario de errores y su solucion
```

## API v2 (backend)

- **Arranque:** `backend/run_backend.bat` → `uvicorn app.v2.main:app` en
  `http://127.0.0.1:8200`, routers bajo el prefijo **`/api/v2`**.
- **Lifespan:** `init_db()` → `verificar_esquema()` (21 tablas) →
  `semilla.sembrar()` (roles/permisos, idempotente) → en `startup`,
  `get_detector()` carga modelo + scaler + umbrales (fail-fast).
- **Routers:** `auth` (login doble token), `acceso` (usuarios/roles),
  `nodos`, `modelo` (artefactos ML), `deteccion` (alertas/diagnóstico),
  `datos` (métricas/eventos), `sistema` (salud/config), `estado` (corridas),
  `telemetria` (push/live/actual).
- **Salud:** `GET /api/v2/salud` verifica BD y esquema.
- **Administrador:** `python crear_admin_v2.py` (no se siembra solo).

## Flujo de telemetría en vivo

```
stream_daemon.py (cada STREAM_INTERVAL, default 7s)
  → login JWT (auto-refresh) + POST /api/v2/telemetria/push  [spool si falla]
      → ring buffer + detector.evaluar (ventana 10 por nodo)
          → normal: Muestras_Normales (alimenta reentreno)
          → anomalía: Predicciones_ML + Alertas + Heatmap + Causas_Raiz
  → GET /api/v2/telemetria/live (SSE) → dashboard
```

- Sin auth en el push (máquina a máquina); el rate limit salta para ese path.
- Los logs del viven viajan en la telemetría; solo se persisten si disparan
  anomalía. Logs del sistema: `backend/logs/` (rotativos).

## Pipeline CRISP-DM (entrenamiento)

1. **Preparación** (`training/nucleo/data_preparation/`, cwd ahí):
   `00_inventario → 01_seleccion → 02_limpieza → 03_transformacion → 04_integracion`
   → `training/output/inventario|limpio|integrado/`.
2. **Modelado** (`training/nucleo/modeling/`): `01_muestras → 02_correlacion →
   03_deteccion_isolation_forest → 04_reglas_motor → 05_diagnostico_resultados`
   → `training/output/modelado/` (+ `generar_copod.py` para el COPOD).
3. **Despliegue:** `promover.py` copia artefactos a `ml/artifacts/` y
   `training/datasets/` (respalda con `.bak_old_<ts>`; aborta si los artefactos
   no coinciden con `config.VARIABLES_MODELO`). Reiniciar backend para recargar.
4. **Reentreno vivo:** `training/entrenar.bat [minutos] [saltar_armado] [saltar_pipeline]`
   = `capturar_live.py` → `construir_dataset.py` (→ `integrado/dataset_reentreno.csv`,
   env `STEELNORT_DATASET_FILE`) → pipeline 01-05 → `generar_copod.py` → `promover.py`.
5. **Automático:** `reentrenar_capturas.py` corre el pipeline cuando hay 1000
   ventanas anómalas nuevas o pasan 30 días (genera candidato, NO promueve).

Variables de entorno clave: `STEELNORT_OUTPUT_DIR`, `STEELNORT_DATASET_SET`
(default `integrado`), `STEELNORT_MODELADO_SET` (default `modelado`),
`STEELNORT_DATASET_FILE` (default `dataset_steelnort_preparado.csv`).

Orquestación interactiva: `python tools/menu_pipeline.py` (o `menu_laboratorio.py`).

## Artefactos

- **Desplegados** (`backend/ml/artifacts/`): `modelo_isolation_forest.joblib`,
  `modelo_copod.joblib`, `scaler.joblib` (54 features), `features_modelo.csv`
  (25 variables = `config.VARIABLES_MODELO`), `reglas_umbrales.csv`
  (q01/q05/q10), `variables_correlacion.csv`, `importancia_variables.csv`.
- **Runtime**: `training/datasets/dataset_muestras_train.pkl`
  (X `(N,10,54)`, scaler, ventana=10).
- Detector online (`app/ml/detector.py`) arma ventanas de 10 muestras por
  nodo, escala con el scaler fijo y evalúa Isolation Forest + COPOD +
  reglas (ensemble Z, `app/ml/ensamble_z.py`, decisión `app/ml/decisor.py`).

## Frontend

- React 19 + Vite; `frontend/src/config.js` fija la base `/api/v2`.
- `npm run dev` → Vite con proxy a Express; `frontend/server/server.js`
  (Node, puerto 8100) proxea `/api/v2` al backend en `:8200` y sirve
  auth, modelo y telemetria/push con rate limit propio.

## Pruebas y utilidades

- `cd backend && .venv\Scripts\python -m pytest tests/ -q`
  - `test_validacion.py` valida los artefactos de `training/output/modelado/`
    contra la config (2 asserts esperan la era 17-vars del set fixture;
    ver `ERRORES_ENCONTRADOS.md`).
  - `simular_telemetria.py` inyecta muestras sintéticas (ancladas al pkl de
    train) contra `/api/v2/telemetria/push`: end-to-end del detector.
  - `probar_seguridad.py`, `test_decisor.py`, `test_detector_zonal.py`.
- `tools/limpieza.py` → borrado controlado por fases (dry-run por defecto).
