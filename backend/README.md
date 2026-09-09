# SteelNort — Backend (API)

Backend de la plataforma SteelNort escrito en **Python + FastAPI**. De
momento expone el modulo de **autenticacion** (login con doble token);
esta disenado para escalar agregando nuevos routers y modelos.

## Requisitos

- Python **3.12** (recomendado; la pila FastAPI/pydantic aun no tiene
  soporte estable para Python 3.14).
- SQL Server accesible (driver ODBC 17 o 18 instalado).
- Conexion Windows (Trusted_Connection) o usuario/contra de SQL.

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

```bash
uvicorn app.main:app --reload --port 8000
```

### Pruebas locales sin SQL Server

Desde la carpeta `backend`, ejecute:

```bat
run_backend.bat test
```

Usa `backend/.venv`, SQLite local (`steelnort_test.db`) y deja la API en
`http://127.0.0.1:8000`. Usuario inicial: `admin@steelnort.com` / `Admin123!`.
Para el frontend: `cd frontend` y ejecute `npm run dev`.

La API queda en `http://localhost:8000`, y la documentacion interactiva
en `http://localhost:8000/docs`.

## Endpoints (login)

| Metodo | Ruta            | Descripcion                                   |
|--------|-----------------|-----------------------------------------------|
| POST   | `/auth/login`   | Autentica y devuelve `{access_token, csrf_token, usuario}` + cookie `csrf_token`. |
| GET    | `/auth/me`      | Devuelve el usuario del token (Bearer).       |
| POST   | `/auth/logout`  | Cierra la sesion y borra la cookie (exige CSRF). |

### Usuarios y permisos

Los permisos se derivan de `Usuarios.usu_rol`, sin tablas adicionales:

| Rol | Permisos |
|-----|----------|
| Administrador | Gestionar usuarios y consultar permisos |
| Supervisor | Consultar usuarios y permisos |
| Operador | Sin permisos administrativos |

| Metodo | Ruta | Descripcion |
|--------|------|-------------|
| GET | `/usuarios` | Lista usuarios activos |
| GET | `/usuarios/roles/permisos` | Consulta permisos agrupados por rol |
| GET | `/usuarios/me/permisos` | Consulta permisos del usuario actual |
| POST | `/usuarios` | Crea un usuario (Administrador + CSRF) |
| PATCH | `/usuarios/{usuario_id}` | Edita un usuario (Administrador + CSRF) |
| DELETE | `/usuarios/{usuario_id}` | Baja logica (Administrador + CSRF) |

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
│   ├── main.py          # Arranque FastAPI + CORS + routers
│   ├── config.py        # Configuracion central (.env, tipada)
│   ├── database.py      # SQLAlchemy engine + sesion + init
│   ├── security.py      # bcrypt, JWT y CSRF
│   ├── seed.py          # Seed del usuario admin si la BD esta vacia
│   ├── models/          # Modelos ORM (uno por dominio)
│   │   ├── __init__.py          # Importa todos los modelos
│   │   └── model_usuario.py     # Usuarios + Sesiones
│   ├── schemas/         # DTOs Pydantic (LoginRequest, TokenResponse...)
│   └── routers/
│       ├── auth.py      # /auth/login, /auth/me, /auth/logout
├── tests/               # (por implementar)
├── requirements.txt
├── .env.example
└── README.md
```

## Escalar

- Nuevo dominio (alertas, reportes, ML, nodos): cree su modelo en
  `app/models/model_<dominio>.py`, impórtelo en `app/models/__init__.py`,
  cree su router en `app/routers/` y registrelo en `main.py`.
- La tabla la crea `init_db()` en el arranque de forma automatica.