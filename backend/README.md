# SteelNort — Backend (API)

Backend de la plataforma SteelNort escrito en **Python + FastAPI**. La unica
API expuesta es la **v2** (`app/v2/`), que monta sus routers bajo el prefijo
`/api/v2` en el puerto **8200** (la v1 fue eliminada; ver rama
`limpieza/organizacion`). Incluye autenticacion de doble token, telemetria en
vivo, deteccion de anomalías, modelos ML, usuarios/roles y sistema.

## Requisitos

- Python **3.12** (recomendado; la pila FastAPI/pydantic aun no tiene
  soporte estable para Python 3.14).
- SQL Server accesible (driver ODBC 17 o 18 instalado).
- Conexion Windows (Trusted_Connection) o usuario/contra de SQL.

> **Politica de entorno (2026):** el unico interpretador de referencia es
> `.venv` (Python **3.12.7**). Se usa **tanto para el backend** (`run_backend.bat`)
> **como para el pipeline de entrenamiento** en `training/nucleo/` (pandas 3.0.x,
> numpy 2.5.x, scikit-learn 1.9.x). No ejecute los scripts de entrenamiento con
> el Python del sistema (3.14) para preservar reproducibilidad.

## Instalacion

```bash
cd backend
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Cree el archivo `.env` copiando `.env.example` y ajuste los valores.

```bash
copy .env.example .env
```

## Configuracion (.env)

- `DATABASE_URL`: cadena de conexion SQLAlchemy para SQL Server.
  - Windows: `mssql+pyodbc://localhost,1433/SteelNort?driver=ODBC+Driver+18+for+SQL+Server&Trusted_Connection=yes&TrustServerCertificate=yes`
  - SQL auth: `mssql+pyodbc://user:pass@localhost,1433/SteelNort?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes`
- `SECRET_KEY`: clave para firmar el JWT (cambiela en produccion).
- `SEED_ADMIN_*`: credenciales del usuario admin inicial. Se crea solo
  si la tabla `Usuarios` esta vacia (el login es `admin@steelnort.com`
  por defecto).
- `CORS_ORIGINS`: origenes permitidos (comas), por defecto el de Vite.

## Ejecucion

```bat
run_backend.bat          :: API v2 en http://127.0.0.1:8200/api/v2
run_backend.bat dev      :: con recarga automatica
```

Equivalente directo: `.venv\Scripts\python -m uvicorn app.v2.main:app --host 127.0.0.1 --port 8200`.

La documentacion interactiva queda en `http://127.0.0.1:8200/docs`.

### Base de datos y primer arranque

- Requiere **SQL Server** con la base `bdSteelNort_v2` (esquema de
  `database/schema.sql` + triggers de `database/instalar_disparadores.sql`).
- El lifespan verifica las 21 tablas y siembra roles/permisos (idempotente).
- El administrador NO se crea solo: ejecute `python crear_admin_v2.py`
  una vez.
- Salud: `GET /api/v2/salud` (BD + esquema).

## Endpoints (prefijo `/api/v2`)

| Metodo | Ruta            | Descripcion                                   |
|--------|-----------------|-----------------------------------------------|
| POST   | `/auth/login`   | Autentica y devuelve `{access_token, csrf_token, usuario}` + cookie `csrf_token`. |
| GET    | `/auth/me`      | Devuelve el usuario del token (Bearer).       |
| POST   | `/auth/logout`  | Cierra la sesion y borra la cookie (exige CSRF). |
| GET    | `/auth/permisos`| Permisos del usuario actual.                  |
| POST   | `/telemetria/push` | Inserta una muestra del daemon (sin auth, rate limit aparte). |
| GET    | `/telemetria/actual` | Ultima muestra publicada por nodo.       |
| GET    | `/salud`        | Estado de la API, BD y esquema.               |

### Usuarios y permisos

Los permisos se derivan de `Usuarios.usu_rol`, sin tablas adicionales:

| Rol | Permisos |
|-----|----------|
| Administrador | Gestionar usuarios y consultar permisos |
| Supervisor | Consultar usuarios y permisos |
| Operador | Sin permisos administrativos |

| Metodo | Ruta | Descripcion |
|--------|------|-------------|
| GET | `/api/v2/usuarios` | Lista usuarios activos |
| GET | `/api/v2/roles-permisos` | Consulta permisos agrupados por rol |
| GET | `/auth/permisos` | Consulta permisos del usuario actual |
| POST | `/api/v2/usuarios` | Crea un usuario (Administrador + CSRF) |
| PATCH | `/api/v2/usuarios/{cod}` | Edita un usuario (Administrador + CSRF) |
| DELETE | `/api/v2/usuarios/{cod}` | Baja logica (Administrador + CSRF) |

Las contrasenas se almacenan con bcrypt y las bajas usan `usu_act`/`fec_eli`.

### Notas de seguridad (doble token)

- `access_token`: JWT firmado. Se envia en el header
  `Authorization: Bearer <token>`. En el frontend se guarda **en
  memoria**.
- `csrf_token`: token opaco. Se entrega en el JSON del login y como
  cookie `csrf_token`. El frontend debe enviarlo en cada request de
  escritura en el header `X-CSRF-Token` y el backend exige que coincida
  con la cookie (doble coincidencia, 403 si no).
- Los campos `reg_usu`, `fec_reg`, `eli_usu`, `fec_eli` (auditoria) se
  gestionan de forma uniforme en todas las tablas.

## Estructura

```
backend/
├── app/
│   ├── v2/               # API v2 (unica app)
│   │   ├── main.py       # Arranque + lifespan (esquema, semilla, detector)
│   │   ├── config.py     # Settings tipados (.env)
│   │   ├── database.py   # SQLAlchemy engine + init_db + verificar_esquema
│   │   ├── seguridad.py  # bcrypt, JWT y CSRF
│   │   ├── models/       # Modelos ORM (21 tablas)
│   │   ├── schemas/      # DTOs Pydantic
│   │   ├── services/     # Logica de negocio
│   │   └── routers/      # auth, acceso, nodos, modelo, deteccion,
│   │                     # datos, sistema, estado, telemetria
│   ├── collector/        # Telemetria: metrics, log_event, xe, stream_daemon
│   ├── ml/               # detector.py, decisor.py, ensamble_z.py (online)
│   ├── config.py         # Config del collector (STREAM_API_URL, credenciales)
│   └── security.py       # Utilidades comunes de seguridad
├── ml/
│   └── artifacts/        # Artefactos ACTIVOS que usa el detector
├── tools/                # Utilidades (ver abajo)
├── training/             # Pipeline CRISP-DM (data_preparation + modeling)
├── tests/                # pytest + utilidades end-to-end
├── run_backend.bat       # Levanta la API v2 en :8200
├── crear_admin_v2.py     # Crea el administrador
├── requirements.txt
├── .env.example
└── README.md
```

## Herramientas (`tools/`) y pruebas (`tests/`)

| Script | Proposito |
|--------|-----------|
| `menu_pipeline.py` | Orquestador: captura normal, anomalias, preparacion, modelado, despliegue y resultados. |
| `menu_laboratorio.py` | Menú de laboratorio (experimentos puntuales). |
| `generar_carga.py` | Genera carga OLTP de trabajo para las capturas. |
| `inyectar_anomalias.py` | Inyecta anomalias en una captura en marcha. |
| `limpieza.py` | Borrado controlado del repositorio (dry-run por defecto). |
| `tests/simular_telemetria.py` | Validador end-to-end: inyecta muestras sintéticas contra `/api/v2/telemetria/push` y verifica que el detector clasifica bien. |

Los run de comparacion/experimentos viven en `training/nucleo/modeling/experimental/`.
Pruebas: `python -m pytest tests/ -q` (ver `docs/ARQUITECTURA.md`).

## Escalar

- Nuevo dominio (alertas, reportes, ML, nodos): cree su modelo en
  `app/v2/models/`, su schema en `app/v2/schemas/`, su router en
  `app/v2/routers/` y registrelo en `app/v2/main.py`.
- La tabla la crea `init_db()` en el arranque de forma automatica.