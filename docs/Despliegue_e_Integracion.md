# Plan de despliegue e integración — SteelNort

**Proyecto:** Sistema inteligente con aprendizaje automático para observabilidad y diagnóstico de anomalías de rendimiento en el OLTP de Steel Nort.

**Documento:** plan de despliegue, arquitectura, exportación del modelo, contratos de la API, integración extremo a extremo, módulos de interfaz, seguridad y pruebas finales.

**Versión:** 1.0 · **Fecha:** 2026-10-15 · **Autor:** equipo SteelNort (tesis)

> Los valores técnicos (puertos, rutas, artefactos, métricas) provienen de artefactos reales del
> repositorio: `backend/app/v2/**`, `backend/app/tools/**`, `frontend/**`, `database/**` y
> `backend/app/tools/output/modelado/**`. No son estimaciones.

---

## 1. Plan de despliegue

### 1.1 Entorno de referencia

El sistema se despliega en **una sola máquina** (host Windows durante el desarrollo y demostración); el
SQL Server OLTP que se monitorea puede vivir en la misma máquina o en otro host de la red.

| Rol del host | Componente | Host / puerto por defecto |
|---|---|---|
| Host de aplicación | API v2 (FastAPI + UVicorn) | `127.0.0.1:8200` |
| Host de aplicación | Plataforma web (Vite, desarrollo) | `127.0.0.1:5173` |
| Host de aplicación | Proxy/middleware Node (Express, producción) | `0.0.0.0:3000` |
| Host de aplicación | Base de la aplicación (`bdSteelNort_v2`) | `localhost:1433` |
| Host monitoreado | SQL Server OLTP de Steel Nort | `SQL_HOST:SQL_PORT` (por defecto `127.0.0.1:1433`) |
| Host monitoreado | Recolector (daemon Python) | proceso local, sin puerto de escucha |

Diagrama de puertos (host de aplicación):

```
  Navegador ──5173──> Vite ──/api/v2──> FastAPI :8200 ──> bdSteelNort_v2 (SQL Server)
                              ──/socket.io──> Express :3000 (Socket.io + Web Push)
  (producción) Navegador ──3000──> Express ──/api──> FastAPI :8200
```

Entorno de demostración en contenedores (referencia, opcional): un contenedor de SQL Server para la
base de la aplicación (`steelnort-db`, `1433` interno) y un contenedor de la API (`steelnort-api`,
`8080` interno). Los contenedores **no** son obligatorios: el despliegue local con los `.bat` cubre la
demostración.

### 1.2 Requisitos

**Software base**

| Requisito | Versión / nota |
|---|---|
| Windows 10/11 (host de desarrollo) | probado en este entorno |
| Python | 3.12.x (venv en `backend/.venv`, interpreter 3.12.7) |
| Microsoft ODBC Driver 18 for SQL Server | requerido por `pyodbc` |
| SQL Server | instancia OLTP monitoreada + base de la aplicación |
| Node.js + npm | para `frontend/` (React 19 + Vite 8) y `frontend/server/` (Express) |
| Git / copia del repositorio | el proyecto **no** es un repositorio Git versionado en este entorno |

**Dependencias Python** (`backend/requirements.txt`, principales): `fastapi==0.143.0`,
`uvicorn==0.54.0`, `SQLAlchemy==2.0.36`, `pyodbc==5.2.0`, `pydantic==2.14.0`, `scikit-learn==1.9.0`,
`numpy==2.5.3`, `pandas==3.0.5`, `scipy==1.18.1`, `joblib==1.6.0`, `matplotlib==3.11.2`,
`PyJWT==2.10.1`, `passlib==1.7.4`, `bcrypt==5.0.0`, `python-dotenv==1.2.4`, `psutil==6.1.1`,
`requests==2.34.2`, `httpx==0.28.1`.

**Dependencias Node** (`frontend/package.json`): React 19, `react-router-dom` 7, `recharts`,
`axios`, `zustand`, `socket.io-client` (vía `services/socket.js`), `vite` 8, `eslint` 10. Servidor:
`express`, `helmet`, `express-rate-limit`, `socket.io`, `web-push`, `dotenv` (`frontend/server/package.json`).

**Configuración (variables de entorno)**

- Backend: `backend/.env` (plantilla `backend/.env.example`) — lectura con prefijo `V2_*`
  heredando `app.config`. Claves: `V2_DATABASE_URL`, `SECRET_KEY`, `ALGORITHM`,
  `ACCESS_TOKEN_EXPIRE_MINUTES`, `V2_CORS_ORIGINS`, `V2_RATE_LIMIT_MAX`, `V2_INTERNAL_TOKEN`,
  `ML_ARTIFACTS_DIR`, `ML_TRAIN_PKL`, `STREAM_*`, `SQL_*`, `XE_FILE_PATH`.
- Servidor Node: `frontend/server/.env` (plantilla `frontend/server/.env.example`) — `PORT`,
  `BACKEND_URL`, `CORS_ORIGIN`, `JWT_SECRET`, límites de rate limiting, `VAPID_*`, `INTERNAL_TOKEN`.
- Frontend: `frontend/.env` — `VITE_API_URL`, `VITE_SOCKET_URL`, `VITE_VAPID_PUBLIC_KEY`.

> `INTERNAL_TOKEN` (Node) y `V2_INTERNAL_TOKEN` (FastAPI) **deben coincidir**: es el token compartido
> para las rutas internas. Igualmente `JWT_SECRET` (Node) debe ser el mismo secreto con que FastAPI
> firma los JWT.

### 1.3 Componentes desplegables

| # | Componente | Artefacto / ruta | Arranque |
|---|---|---|---|
| 1 | Base de la aplicación | `database/schema_bdsteelnort.sql` (+ `migracion_*.sql`, `inserts.sql`) | ejecutar script en SQL Server |
| 2 | API v2 | `backend/app/v2/main.py` | `backend\run_backend.bat` → `uvicorn app.v2.main:app --host 127.0.0.1 --port 8200 --reload` |
| 3 | Modelo ML (bundle) | `backend/app/tools/output/modelado/produccion/` | se carga solo al iniciar la API (`get_detector()` en `startup_event`) |
| 4 | Recolector | `backend/app/tools/collector/stream.py` | `python -m app.tools.collector.stream` |
| 5 | Plataforma web (dev) | `frontend/` | `npm run dev` (Vite, `:5173`) |
| 6 | Proxy/middleware Node | `frontend/server/server.js` | `node server.js` (`:3000`) |
| 7 | Servicio de notificaciones | `frontend/server/push.js` + `websocket.js` | arranca con el servidor Node |
| 8 | Herramientas de modelado/indicadores | `backend/app/tools/modelado/**`, `calcular_indicadores.py` | por lotes (Python) |

### 1.4 Responsables

| Actividad | Responsable | Apoyo |
|---|---|---|
| Aprovisionar SQL Server y la base de la aplicación | Encargado de TI de Steel Nort | Desarrollador |
| Despliegue de la API v2 y del modelo | Desarrollador (tesista) | — |
| Despliegue de la plataforma web y del proxy Node | Desarrollador (tesista) | — |
| Operación del recolector en el host monitoreado | Encargado de TI | Desarrollador |
| Administración de usuarios/roles (RF1) | Encargado de TI | Desarrollador |
| Verificación de indicadores y evidencias | Desarrollador (tesista) | Asesor |
| Capacitación y manual de usuario | Desarrollador (tesista) | Encargado de TI |

> Completar la columna de nombres reales antes de la entrega.

### 1.5 Runbook (orden de arranque)

1. Levantar SQL Server y aplicar `database/schema_bdsteelnort.sql` (+ migraciones). Comprobar con
   `GET /api/v2/salud` que `tablas_ok` coincide con el esquema esperado y `tablas_faltantes` viene vacío.
2. Copiar `backend/.env.example` → `backend/.env` y rellenar credenciales, `SECRET_KEY` y
   `V2_INTERNAL_TOKEN`.
3. Arrancar la API: `backend\run_backend.bat`. En el log debe verse
   *"Modelos de Machine Learning cargados correctamente."* y el seed idempotente de roles/permisos/administrador.
4. (Producción) Compilar el frontend (`npm run build`) y arrancar `frontend/server` (`node server.js`);
   (Desarrollo) `npm run dev` en `frontend/` con el proxy de Vite a `:8200`.
5. Arrancar el recolector en el host monitoreado (`python -m app.tools.collector.stream`).
6. Verificar el flujo: `GET /api/v2/telemetria/actual` devuelve la última muestra; el dashboard y las
   alertas se alimentan en tiempo real por Socket.io.
7. (Opcional) Programar el servicio de Windows / tarea para el recolector y el servidor Node.

---

## 2. Arquitectura

Flujo de datos extremo a extremo:

```
┌──────────────┐   DMV + Extended Events + errorlog    ┌───────────────┐
│  SQL Server  │ ────────────────────────────────────> │  RECOLECTOR   │
│  OLTP Steel  │                                       │ stream.py     │
│  Nort        │ <────── consultas de métricas ─────── │ (cada ~2 s)   │
└──────────────┘                                       └───────┬───────┘
                                                               │ POST /api/v2/telemetria/push
                                                               │ (X-Internal-Token + JWT)
                                                               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                              API v2                      │
│                                                                          │
│  telemetria/push ──> caché RAM (/actual)                                 │
│        │                                                                 │
│        ├──> MODELO: detector.evaluar(nodo, muestra)  [ENSEMBLE_LOF_ELL]  │
│        │        z-score por ventana móvil (10) sobre 25 variables        │
│        │        + clasificador de tipo (top-2)                           │
│        │                                                                 │
│        ├──> ¿anomalía? ──> persistir_anomalia() ──> alerta + diagnóstico │
│        │                                          (variables, tipo,       │
│        │                                           severidad, causa raíz)│
│        └──> eventos/logs ──> registrar_eventos/logs (ring buffer)        │
│                                                                          │
│  deteccion / informes / sistema / modelo / acceso / auth / nodos / …    │
└───────────────┬───────────────────────────────────────────┬─────────────┘
                │ REST (JWT)                                 │ Web Push (interno)
                ▼                                            ▼
┌──────────────────────────────────┐        ┌──────────────────────────────┐
│  PLATAFORMA WEB (React + Vite)   │        │                │
│  Login · Inicio · Dashboard ·    │<──ws── │  proxy /api, Socket.io,      │
│  Alertas · Reportes · Config.    │        │  Web Push (VAPID), helmet    │
└──────────────────────────────────┘        └──────────────────────────────┘
```

**Etapas**

1. **SQL Server (fuente).** El OLTP de Steel Nort expone métricas por DMV, eventos por Extended
   Events y el error log. El sistema **no** modifica el OLTP: solo lee.
2. **Recolector (`tools/collector/`).** `stream.py` construye la muestra (SO vía `psutil`, SQL Server
   vía DMV, agregados de XE como `batch_count` / `batch_duration_*_ms` / `events_wait_count`, y el
   errorlog) y la publica en `POST /api/v2/telemetria/push`. Ante caída de la API escribe a un
   **spool local JSONL** y lo reenvía en el siguiente ciclo (tolerancia a fallos).
3. **Modelo ML (`tools/motor/detector.py`).** Mantiene por nodo una **ventana móvil** de 10 muestras y
   puntúa cada ventana llena con el ensamble **ENSEMBLE_LOF_ELL** (LOF + Elliptic Envelope) sobre las
   25 variables normalizadas. Emite score, umbral (q01 por defecto) y zona.
4. **API v2 (`app/v2/`).** Recibe la muestra, actualiza la caché en RAM, evalúa el modelo, registra
   eventos/logs y, si hay anomalía, **persiste** la alerta y su diagnóstico.
5. **Plataforma web (`frontend/`).** Consume la API por REST (JWT) y recibe telemetría/notificaciones
   en tiempo real por Socket.io y Web Push.

**Decisiones de diseño relevantes**

- **Ingesta en RAM** (`MEMORIA_CACHE` en `routers/telemetria.py`) para lecturas rápidas del dashboard.
- **Diagnóstico acumulativo por evento**: mientras una alerta sigue activa, sus variables afectadas se
  **amplían** (no se congela en la primera ventana); esto sostiene el indicador I-3.3.
- **Separación v1/v2**: la base y la API v2 (`bdSteelNort_v2`, prefijo `/api/v2`) coexisten con la v1.
- **Escalabilidad (RNF4)**: agregar variables o fuentes no exige tocar el detector; el ensamble se
  autoelige según los componentes disponibles.

---

## 3. Exportación del modelo

El bundle de producción se genera con `backend/app/tools/modelado/04_exportar_produccion.py` a partir
de `artefactos_modelo.pkl` (fase de modelado). Se escribe en un directorio nuevo, sin modificar lo
existente:

```
backend/app/tools/output/modelado/produccion/
├── modelo_lof.joblib                # componente LOF
├── modelo_elliptic.joblib           # componente Elliptic Envelope
├── modelo_isolation_forest.joblib   # componente alterno (ENSEMBLE_Z)
├── scaler.joblib                    # normalizador (alineado a las features del train)
├── features_modelo.csv              # orden EXACTO de columnas del scaler (25)
├── dataset_muestras_train.pkl       # features completas + X_train 3D (reentreno)
├── clasificador_tipo.joblib         # clasificador de tipo de anomalía (top-2)
└── meta.json                        # metadatos del ensamble, features y umbrales
```

**ENSEMBLE desplegado: `ENSEMBLE_LOF_ELL`** (según `meta.json`)

| Campo | Valor |
|---|---|
| `ensemble` | `ENSEMBLE_LOF_ELL` |
| `componentes` | `LOF`, `ELLIPTIC` |
| `ventana` | `10` |
| `n_features` | `25` |
| `n_train` | `353` |

**Normalizador (`scaler.joblib`).** Estandariza cada variable con la media/desviación del conjunto de
entrenamiento; `features_modelo.csv` fija el orden de columnas para evitar cruces de variables. El
detector aplica el mismo `scaler` a cada muestra antes de puntuar.

**Las 25 variables del modelo** (`meta.json` → `features`):

```
cpu_usr, cpu_sys, cpu_wai, memory_percent, memory_used_mb, page_life_expectancy,
disk_read_per_sec, disk_write_per_sec, net_send_per_sec, net_recv_per_sec, load1,
active_sessions, active_requests, transactions_per_sec, long_queries,
long_transactions, api_latency_ms, api_status, lock_waits, total_locks,
deadlocks_per_sec, events_wait_count, batch_count, batch_duration_avg_ms,
batch_duration_max_ms
```

> La definición canónica vive en `backend/app/tools/modelado/modelado_config.py`
> (`VARIABLES_MODELO`, 25; `VENTANA=10`). Algunas métricas de footprint
> (`total_writes, total_reads, page_reads, wait_log_count, wait_io_count, query_count,
> wait_lck_count`) se recolectan pero **no** alimentan el modelo.

**Umbrales** (`meta.json` → `umbrales`):

| Cuantil | Valor | Uso |
|---|---|---|
| `q10` | `-0.574247514317584` | umbral laxo |
| `q05` | `-1.7199110820494143` | umbral intermedio |
| `q01` | `-3.5574499490984497` | **umbral de producción** (1 % de cola) |

El detector decide anomalía cuando el score de la ventana cae por debajo del umbral configurado
(`q01` por defecto). El puntaje es **menor = más anómalo**.

**Regenerar el bundle** (desde `backend/app/tools/modelado/`):

```bat
python 04_exportar_produccion.py
```

El bundle resultante es el que consume `tools/motor/detector.py` en producción (`ML_ARTIFACTS_DIR`
apunta a `app/tools/output/modelado/produccion`).

---

## 4. API (contratos modelo ↔ plataforma)

Prefijo global de la v2: **`/api/v2`**. Todas las rutas de negocio exigen **JWT** (`Authorization:
Bearer <token>`) y la mayoría un **permiso** `modulo:accion` (`leer` / `crear` / `editar` / `eliminar`);
el rol *Administrador* lo tiene todo.

**Autenticación y acceso** (`routers/auth.py`, `routers/acceso.py`)

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/api/v2/auth/login` | Inicia sesión, devuelve `access_token` |
| `GET` | `/api/v2/auth/me` | Usuario del token |
| `GET` | `/api/v2/auth/permisos` | Permisos efectivos del usuario |
| `POST` | `/api/v2/auth/logout` | Cierra la sesión |
| `GET/POST/PATCH/DELETE` | `/api/v2/acceso/usuarios` … | Usuarios, roles, permisos, asignaciones, sesiones |

**Ingesta del modelo** (`routers/telemetria.py`) — *punto de unión datos ↔ modelo*

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/api/v2/telemetria/push` | **Ruta interna**: recibe la muestra, evalúa el modelo y persiste anomalías. Exige `X-Internal-Token` |
| `GET` | `/api/v2/telemetria/actual` | Última muestra en RAM (tarjetas del dashboard, en vivo) |

**Detección y diagnóstico** (`routers/deteccion.py`) — RF5

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/api/v2/deteccion/alertas` | Lista de alertas |
| `GET` | `/api/v2/deteccion/alertas/{cod}` | Detalle de una alerta |
| `GET` | `/api/v2/deteccion/alertas/{cod}/informe` | **Informe completo** de la anomalía (variables, tipo, severidad, causa) |
| `POST` / `PATCH` / `DELETE` | `/api/v2/deteccion/alertas[/{cod}]` | Abrir / editar-resolver / descartar alerta |
| `GET/POST` | `/api/v2/deteccion/alertas-variables` | Variables afectadas por alerta |
| `GET/POST/DELETE` | `/api/v2/deteccion/causas` | Causa raíz |
| `GET` | `/api/v2/deteccion/heatmap` | Mapa de calor de anomalías |

**Modelo** (`routers/modelo.py`) — ciclo de vida ML

| Método | Ruta | Descripción |
|---|---|---|
| `GET/POST/PATCH/DELETE` | `/api/v2/modelo/modelos[/{cod}]` | CRUD de modelos |
| `POST` | `/api/v2/modelo/modelos/{cod}/activar` | Activa un modelo en producción |
| `GET/POST` | `/api/v2/modelo/predicciones` | Predicciones persistidas |
| `GET/POST` | `/api/v2/modelo/deriva` | Medidas de deriva (drift) |
| `GET/POST/PATCH` | `/api/v2/modelo/reentrenamientos[/{cod}]` | Reentrenamientos y sus pasos |

**Informes** (`routers/informes.py`) — RF7

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/api/v2/informes/resumen` | Resumen del periodo |
| `GET` | `/api/v2/informes/anomalias` | Anomalías detalladas |
| `GET` | `/api/v2/informes/alertas` | Historial de alertas |
| `POST` | `/api/v2/informes/generar` | Genera un informe (CSV/JSON) |
| `GET` / `DELETE` | `/api/v2/informes/exportados[/{nombre}]` | Lista / descarga / borra exportaciones |

**Dashboard / indicadores** (`routers/sistema.py`)

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/api/v2/sistema/resumen` | Cifras de la pantalla de inicio |
| `GET` | `/api/v2/sistema/resumen/heatmap` | Celdas del mapa de calor de un día |
| `GET` | `/api/v2/sistema/resumen/disponibilidad` | Disponibilidad de los últimos días |
| `GET` | `/api/v2/sistema/resumen/transacciones` | Promedio diario de transacciones |
| `GET` | `/api/v2/sistema/conexiones` | Estado de conexiones |
| `GET/PUT/DELETE` | `/api/v2/sistema/configuracion[/{clave}]` | Parámetros del sistema |
| `GET` | `/api/v2/sistema/auditoria` | Registro de auditoría |

**Datos crudos** (`routers/datos.py`, `routers/nodos.py`, `routers/estado.py`)

| Método | Ruta | Descripción |
|---|---|---|
| `GET/POST` | `/api/v2/datos/metricas`, `/eventos`, `/logs`, `/cargas` | Series crudas recolectadas |
| `GET` | `/api/v2/nodos/instancias`, `/nodos/sesiones-sql` | Instancias y conexiones observadas |
| `GET` | `/api/v2/estado/conexiones` | Estado SQL Server + sesión XE del host monitoreado |

**Salud / notificaciones / internos**

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/api/v2/salud` | Estado de la API + `tablas_ok` / `tablas_faltantes` (usado por I-5.4) |
| `GET/PATCH/POST/DELETE` | `/api/v2/notificaciones…` | Notificaciones del usuario (contador, marcar leída) |
| `GET` | `/api/v2/internal/push/suscripciones` | **Interno** (Node): suscripciones Web Push activas |
| `POST` | `/api/v2/internal/push/{psu_cod}/uso` | **Interno** (Node): marca una suscripción como usada |

> Las rutas `internal/*` (y `telemetria/push`) se protegen con el header compartido
> `X-Internal-Token` en lugar de JWT. El documento interactivo de la API está disponible en
> `/docs` (Swagger UI) cuando la API está en ejecución.

---

## 5. Integración completa (flujo en vivo)

Secuencia de un ciclo de telemetría (intervalo por defecto `STREAM_INTERVAL=2` s):

1. **Captura.** El recolector arma la muestra: SO (`metrics.get_system_metrics`), SQL Server
   (`get_sql_server_metrics`, `get_business_locks`), API de negocio (`get_api_metrics`) y agregados
   de Extended Events (`batch_count`, `batch_duration_avg_ms`, `batch_duration_max_ms`,
   `events_wait_count`).
2. **Publicación.** `POST /api/v2/telemetria/push` con `X-Internal-Token` (+ JWT si hay sesión). Si la
   API no responde, la muestra va al **spool** y se reintenta después.
3. **Ingesta.** `routers/telemetria.py` guarda la muestra en `MEMORIA_CACHE[nodo]` (para
   `/telemetria/actual`) y registra eventos/logs en el ring buffer.
4. **Detección.** `detector.evaluar(nodo, muestra)` llena la ventana móvil; al completar 10 muestras,
   normaliza las 25 variables con `scaler` y calcula el score del ensamble `ENSEMBLE_LOF_ELL`.
5. **Decisión.** Si el score < umbral (q01) → anomalía. Se calcula la **zona** y, con el
   `clasificador_tipo`, los **tipos candidatos** (top-2). El resultado se devuelve en la respuesta
   del `push` (`es_anomalia`, `alerta_activa`, `alerta_nueva`, `score`, `umbral`, `zona`).
6. **Persistencia.** `services/anomalia_v2.persistir_anomalia()` crea la **alerta**, su **predicción**,
   las **variables afectadas** y la **causa raíz**. Si la alerta ya estaba activa, **amplía** las
   variables del evento (`_ampliar_alerta`) en lugar de crear una nueva.
7. **Diagnóstico.** `services/clasificador_tipo.py` expone el **tipo** (top-1 / top-2) y su resumen;
   el detalle se sirve en `GET /deteccion/alertas/{cod}/informe` (variables afectadas, tipo,
   severidad, causa raíz).
8. **Difusión.** Las alertas nuevas disparan **notificaciones**: `services/notificador.py` +
   `POST` interno al servidor Node (`/internal/notificar`), que envía **Web Push** (VAPID) a los
   navegadores suscritos y **Socket.io** emite los eventos en tiempo real.
9. **Visualización.** El **dashboard** (`/sistema/resumen`, `/telemetria/actual`), la pantalla de
   **alertas** y la de **reportes** muestran telemetría, anomalías y diagnósticos.

```
SQL Server ──> recolector ──> POST /telemetria/push ──> detector ──> ¿anomalía?
                                                          │            │ sí
                                                          │            ▼
                                                          │     persistir_anomalia ──> alerta
                                                          │            │              + diagnóstico
                                                          │            ▼
                                                          └──> notificador ──> Express ──> Web Push / Socket.io
                                                                                      │
                                                                                      ▼
                                                                              Dashboard / Alertas / Reportes
```

**Idempotencia y recuperación.** El seed de arranque (roles, permisos, administrador) es idempotente;
el recolector tolera caídas con el spool; la API reintenta el login cuando el token expira (401).

---

## 6. Módulos de las interfaces

Rutas de la SPA definidas en `frontend/src/App.jsx`, protegidas por `RequireAuth` (sesión) y
`RequirePermiso` (permiso del rol). El backend vuelve a comprobar el permiso en cada llamada.

| Módulo | Ruta SPA | Página | Permiso | RF | Estado |
|---|---|---|---|---|---|
| Inicio de sesión | `/` | `Login.jsx` | pública | RF1 | Implementado |
| Página principal | `/inicio` | `Inicio.jsx` | `tablero:leer` | RF6 | Implementado |
| Dashboard | `/dashboard` | `Dashboard.jsx` | `tablero:leer` | RF6 | Implementado |
| Alertas y diagnóstico | `/alertas` | `Alertas.jsx` | `deteccion:leer` | RF5 | Implementado |
| Reportes | `/reportes` · `/reportes-v2` | `v2/Reportes_v2.jsx` | `datos:leer` | RF7 | Implementado |
| Reportes (v1) | `/reportes-v1` | `Reportes.jsx` | `datos:leer` | RF7 | Disponible (legado) |
| Configuración | `/configuracion` | `Configuracion.jsx` | `sistema:leer` | RF1 / RF10 | Implementado |

**Componentes reutilizables** (`frontend/src/components/`): `Sidebar.jsx`, `Topbar.jsx`,
`ModalUsuario.jsx`, `RolesPermisosModal.jsx`, `UserRolesModal.jsx`, `ModalNotificaciones.jsx`,
`CorrelacionRaiz.jsx`, `HistoriaSesion.jsx`.

**Sobre "módulos que faltan".** En el estado actual del repositorio, **alertas, diagnóstico y
reportes ya existen** como pantallas:
- **Alertas** (`/alertas`) cubre RF5: lista y detalle de alertas con variables afectadas, tipo y
  severidad; el **diagnóstico** se muestra dentro del informe de la alerta
  (`GET /deteccion/alertas/{cod}/informe`), no como una pantalla separada. Si se desea una pantalla
  de diagnóstico dedicada, se puede derivar de ese informe sin cambios de backend.
- **Reportes** (`/reportes`) cubre RF7: resumen del periodo, exportación a CSV/JSON y descarga de
  informes generados.

Pendientes reales de interfaz (si se quieren cerrar): pantalla dedicada de **diagnóstico**, y la
**encuesta de satisfacción** (I-4.3 / RNF5), que no es una pantalla sino un instrumento.

---

## 7. Seguridad y control de acceso

| Control | Dónde | Detalle |
|---|---|---|
| **Autenticación JWT** | `app/security.py`, `routers/auth.py` | Login usuario/clave → `access_token` firmado (HS256, expiración `ACCESS_TOKEN_EXPIRE_MINUTES`). El token va en `Authorization: Bearer`. |
| **Autorización por roles/permisos** | `app/v2/seguridad.py` | Dependencias `usuario_actual` y `requiere_permiso("modulo:accion")`. El permiso sale de `rol_permiso → permiso`; el rol *Administrador* lo tiene todo. Acciones: `leer`, `crear`, `editar`, `eliminar`. |
| **CSRF (doble-envío)** | `backend/app/v2/csrf.py` + `frontend/src/services/api.js` | Middleware que emite una cookie `csrf_token` (legible) y exige la cabecera `X-CSRF-Token` con el mismo valor en toda escritura de `/api/v2` (403 si falta o no coincide). Exento en `/auth/login` y en las rutas internas (`X-Internal-Token`). Defensa en profundidad: la v2 no usa cookies de sesión (JWT en memoria), por lo que el control es redundante hoy pero queda probado si se migra a cookies. |
| **Auditoría** | `app/v2/auditoria.py` | Middleware transversal: cada escritura (`POST/PUT/PATCH/DELETE`) sobre `/api/v2` y cada acceso **denegado (403)** escribe una fila en `dbo.auditoria` (`aud_usu`, `aud_accion`, `aud_recurso`, `aud_resultado`, `aud_ip`, `aud_fec`). Se guarda tras responder, en un hilo aparte. Consultable en `GET /sistema/auditoria`. |
| **Cabeceras de seguridad** | `app/v2/cabeceras.py` (API) y `frontend/server/middleware/security.js` (Helmet) | `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`; en Node: CSP, HSTS (producción), `frame-ancestors: none`, `referrerPolicy`. |
| **Rate limiting** | `app/v2/limites.py` (API) y `middleware/rateLimit.js` (Node) | API: ventana deslizante por IP (`V2_RATE_LIMIT_MAX`), responde 429 con `Retry-After`. Node: `apiLimiter`, `authLimiter` (solo cuenta fallos → anti fuerza bruta), `modelLimiter` (metadatos ML) e `ingestLimiter` (ingesta del daemon, solo localhost). |
| **Protección de artefactos ML** | `middleware/modelProtection.js` | Bloquea (403) accesos a `.joblib/.pkl/.h5/.onnx/...` y a `features_modelo.csv`, `reglas_umbrales.csv`, `artifacts/`: el modelo no se expone como archivo. |
| **Bloqueo de archivos sensibles** | `middleware/security.js` | Niega `.env`, `.git`, `node_modules`, `.venv`, `__pycache__`, `*.pem/*.key/*.crt/*.p12`, `logs/`, y detecta **path traversal** (`../`, `..%2f`). |
| **Token interno** | `routers/push_interno.py`, `routers/telemetria.py` | Rutas internas (`internal/*`, `telemetria/push`) exigen `X-Internal-Token` = `V2_INTERNAL_TOKEN`; no se exponen al frontend. |
| **Comunicación segura (TLS)** | `docs/Configuracion_TLS.md` | HTTPS en producción; el CSP fuerza HTTPS (`upgrade-insecure-requests`) solo en `NODE_ENV=production`. |
| **Privacidad (Ley N.° 29733)** | `services/privacidad.py` | Minimización y enmascarado del `sql_text` que pueda contener datos personales. |

**Gestión de usuarios (RF1 / RF10).** `routers/acceso.py` implementa alta/edición/baja de usuarios y
roles, asignación de permisos y listado de sesiones; la pantalla de Configuración lo expone
(`ModalUsuario.jsx`, `RolesPermisosModal.jsx`). Ver `docs/Alineacion_RF.md` para su justificación.

---

## 8. Pruebas finales

### 8.1 Pruebas funcionales (unidad/integración)

Suite `backend/tests/`: `test_detector.py`, `test_diagnostico.py`, `test_privacidad.py`, con
`conftest.py`. Medición del indicador **I-5.3 (tasa de funcionamiento ≥ 90 %)** con
`indicadores/15_tasa_pruebas.py`, que ejecuta la suite y escribe `tasa_pruebas.json`.

Resultado medido (`backend/app/tools/output/modelado/indicadores/tasa_pruebas.json`):

| Casos totales | Exitosos | Fallidos | Errores | Tasa | Meta | Cumple |
|---|---|---|---|---|---|---|
| 18 | 18 | 0 | 0 | **100 %** | ≥ 90 % | ✅ |

Ejecución manual: `cd backend && .venv\Scripts\python -m pytest tests -q`.

### 8.2 Pruebas de integración

Verificación extremo a extremo del flujo (SQL Server → recolector → modelo → API → web):

1. `GET /api/v2/salud` → 200 con `tablas_ok` completo y `tablas_faltantes = []`.
2. `POST /api/v2/telemetria/push` (con `X-Internal-Token`) → `estado: evaluado` con `score`,
   `umbral` y `zona`.
3. `GET /api/v2/telemetria/actual` → última muestra del servidor real.
4. `GET /api/v2/deteccion/alertas` y `GET /api/v2/deteccion/alertas/{cod}/informe` → alerta con su
   diagnóstico.
5. `GET /api/v2/estado/conexiones` → SQL Server y sesión XE conectados.
6. `GET /api/v2/informes/generar` → archivo exportado y descargable.

### 8.3 Tiempos de respuesta (≤ 3 s)

Indicadores **I-4.2 / I-5.2 (meta ≤ 3 s)**, medidos con `indicadores/12_tiempos_operacion.py` sobre la
API en ejecución (operaciones: dashboard, anomalías, alertas, reporte de resumen). Salida:
`tiempos_operacion.json` / `tiempos_operacion.csv`.

Referencia registrada: los endpoints clave responden en el orden de **~181–224 ms** (≤ 3 s), muy por
debajo de la meta. El script recalcula media y P95 por operación y marca `cumple` con el umbral global.

```bat
python indicadores/12_tiempos_operacion.py --usuario admin --clave "<clave>" --n 30
```

### 8.4 Tasa de funcionamiento y disponibilidad

- **Tasa de funcionamiento (I-5.3)**: 100 % (ver 8.1).
- **Disponibilidad (I-5.4, meta ≥ 95 %)**: `indicadores/13_disponibilidad.py` hace ping periódico a
  `GET /api/v2/salud` durante una ventana de observación y calcula
  `pings_ok / pings_totales`. Salida: `disponibilidad.json`.

```bat
python indicadores/13_disponibilidad.py --duracion 3600 --intervalo 10
```

> **Nota de método:** durante la medición **no** se debe reiniciar el backend (`--reload`) ni editar
> archivos `.py` bajo `backend/`: provoca falsos "timed out" que bajan artificialmente la
> disponibilidad. Medir con el sistema estable.

### 8.5 Resumen de indicadores de esta fase

| Indicador | Meta | Valor | Estado |
|---|---|---|---|
| I-2.1 F1 de detección | ≥ 85 % | 0.9639 | ✅ |
| I-3.1 Precisión por tipo (top-2) | ≥ 90 % | 96.1 % (ventana) / 91.7 % (evento) | ✅ (criterio top-2) |
| I-3.3 Efectividad del diagnóstico | ≥ 85 % | 91.67 % (22/24, nivel evento) | ✅ |
| I-5.1 Recall | ≥ 85 % | 100 % | ✅ |
| I-5.2 Tiempo de respuesta | ≤ 3 s | ≤ 0.5 s | ✅ |
| I-5.3 Tasa de funcionamiento | ≥ 90 % | 100 % | ✅ |
| I-5.4 Disponibilidad | ≥ 95 % | (ver `disponibilidad.json`) | medir |
| I-3.2 Coincidencia de severidad | ≥ 90 % | sin *ground truth* en escenarios | ⚠️ limitación |

> Detalle y evidencia por indicador en `docs/Indicadores_v2.md` y `docs/guia_indicadores.md`.
> **I-3.1** se declara con el criterio **top-2** (el sistema muestra dos tipos candidatos): el top-1
> no alcanza el 90 % por la confusión `fault2 ↔ fault5`. **I-3.2** no es medible con los escenarios
> actuales (solo traen `tipo, inicio, fin`, sin severidad esperada).

---

## 9. Documentación y capacitación

### 9.1 Manual de usuario

| Documento | Contenido | Estado |
|---|---|---|
| `docs/Despliegue_e_Integracion.md` | este documento (despliegue, arquitectura, API, seguridad, pruebas) | ✅ |
| `docs/guia_indicadores.md` | guía de indicadores con valores medidos y notas de honestidad | ✅ |
| `docs/Indicadores_v2.md` | definición de indicadores, requisitos RF/RNF y trazabilidad | ✅ |
| `docs/Alineacion_RF.md` | alineación RF1–RF7 (+RF10) con módulos reales | ✅ |
| `docs/Evidencia_seguridad.md` | evidencias de los controles de seguridad | ✅ |
| `docs/Matriz_riesgos.md` | matriz de riesgos | ✅ |
| **Manual de usuario (operativo)** | uso paso a paso de la plataforma (login, dashboard, alertas, reportes, configuración) para el encargado de TI | ⏳ pendiente |
| `frontend/README.md` | notas de la plataforma | ✅ |

### 9.2 Registro de capacitación

Formato sugerido para dejar constancia de la capacitación al encargado de TI:

| Campo | Valor |
|---|---|
| Fecha y hora | *(pendiente)* |
| Modalidad | Presencial / remota |
| Facilitador | Desarrollador (tesista) |
| Participantes | Encargado de TI, operadores (nombres y firmas) |
| Temario | (1) arranque y operación; (2) lectura del dashboard; (3) gestión de alertas y diagnóstico; (4) reportes; (5) administración de usuarios/roles; (6) buenas prácticas y recuperación ante fallos |
| Material | Manual de usuario + este documento |
| Evidencia | Lista de asistencia firmada y, si aplica, captura de la sesión |

> La capacitación **aún no se ha registrado**; se recomienda realizarla tras estabilizar el despliegue
> y anexar la lista de asistencia como evidencia (relevante para el criterio de Usabilidad, RNF5).

---

## 10. Limitaciones y siguientes pasos

**Limitaciones conocidas (declaradas de forma honesta)**

1. **I-3.2 (severidad) no es medible** con los escenarios actuales: los archivos de escenario
   (`anomalias_timeline.csv`, `origen.json`) solo traen `tipo, inicio, fin`, sin severidad esperada.
   Además la severidad emitida satura (M 4 / A 20). Requiere etiquetas de severidad por escenario.
2. **I-3.1 en top-1 no alcanza el 90 %** por la confusión `fault2 ↔ fault5` (~66 % ventana / ~75 %
   evento). Se adopta el criterio **top-2** (96.1 % / 91.7 %), defendible porque el sistema muestra
   dos candidatos.
3. **I-4.3 (satisfacción) pendiente**: la encuesta de usuarios no se ha aplicado.
4. **Capacitación sin registro** (ver §9.2).
5. **Sin control de versiones**: el proyecto no está bajo Git en este entorno; no hay red de
   seguridad para revertir cambios.
6. **Un solo nodo monitoreado** por defecto (`Servidor Negocio`); la ingesta soporta varios nodos,
   pero no se ha ejercitado en producción más de uno.
7. **Documentación de API**: el contrato se navega en Swagger (`/docs`); no hay un OpenAPI versionado
   como artefacto.

**Siguientes pasos**

1. Etiquetar severidad esperada en los escenarios → habilitar I-3.2.
2. Registrar la capacitación y publicar el manual de usuario operativo (§9).
3. Aplicar la encuesta de usabilidad → cerrar I-4.3 / RNF5.
4. Medir la disponibilidad (I-5.4) con el sistema estable y anexar `disponibilidad.json`.
5. Versionar el proyecto en Git y automatizar la regeneración de artefactos e indicadores
   (`calcular_indicadores.py`, `indicadores/*.py`).
6. Opcional: pantalla dedicada de **diagnóstico** (derivada del informe de alerta) y multi-nodo real.

---

### Anexo — Artefactos de evidencia

| Artefacto | Ruta |
|---|---|
| Bundle del modelo | `backend/app/tools/output/modelado/produccion/` |
| Metadatos del modelo | `.../produccion/meta.json` |
| Índice de calidad de datos | `.../indicadores/calidad_indice.json` |
| F1 / validación honesta | `.../indicadores/honesto.json` |
| Diagnóstico (I-3.3) | `.../indicadores/diagnostico_final.json` |
| Clasificador de tipo (I-3.1) | `.../indicadores/clasificador_tipo.json`, `clasificador_tipo_cuando.json` |
| Disponibilidad (I-5.4) | `.../indicadores/disponibilidad.json` |
| Tiempos de operación (I-5.2) | `.../indicadores/tiempos_operacion.json` / `.csv` |
| Tasa de pruebas (I-5.3) | `.../indicadores/tasa_pruebas.json` |
| Reporte de tests | `.../indicadores/reporte_pytest.xml` |
| Gráficos por indicador | `.../indicadores/graficos/` |
