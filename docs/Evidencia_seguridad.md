# Evidencia — Seguridad y Protección (Sprint 1)

**Fecha:** 2026-10-13/14 · **Modelo/base:** `bdSteelNort_v4` (25 tablas) · **API:** `http://127.0.0.1:8200` (vía proxy Vite `http://127.0.0.1:5173/api/v2`)

Este documento guarda la **salida real** de las pruebas hechas para el Sprint 1. Cada bloque se puede
reproducir con los comandos indicados. No hay cifras inventadas: todo salió de la corrida del
2026-10-14.

---

## 1. Registro de auditoría (`dbo.auditoria`)

### 1.1 Login correcto → fila con usuario (acción `LOGIN`)
```
POST /api/v2/auth/login  josias/********  ->  HTTP 200
```
Fila generada (el login se registra aparte porque el token no viaja en esa petición):
```
aud_cod=3  aud_usu=1  aud_accion=LOGIN  aud_recurso=/api/v2/auth/login  aud_resultado=200  aud_ip=127.0.0.1
```

### 1.2 Login fallido → fila sin usuario (acción `LOGIN_FAIL`)
```
POST /api/v2/auth/login  qa_auditoria/clave_mala  ->  HTTP 401   (x5)
```
```
aud_cod=8..12  aud_usu=NULL  aud_accion=LOGIN_FAIL  aud_resultado=401
```

### 1.3 Cuenta bloqueada → 429 (acción `LOGIN_BLK`)
Tras 5 fallos:
```
POST /api/v2/auth/login  qa_auditoria/clave_mala  ->  HTTP 429
Retry-After: 899
{"detail":"Cuenta bloqueada por intentos fallidos. Intente mas tarde."}
```
```
aud_cod=13  aud_usu=NULL  aud_accion=LOGIN_BLK  aud_resultado=429
```

### 1.4 Cambio auditado (alta y baja de usuario) y acceso denegado (403)
```
POST   /api/v2/acceso/usuarios   -> 201   (aud_cod=6,  usd_cod=5)
DELETE /api/v2/acceso/usuarios/5 -> 200   (aud_cod=15)
GET    /api/v2/sistema/configuracion (rol Operador) -> 403  (aud_cod=20)
```
El 403 se registra aunque sea un `GET`: el middleware audita **toda escritura y todo acceso denegado**.

### 1.5 Consulta del registro (`GET /api/v2/sistema/auditoria`)
```
GET /api/v2/sistema/auditoria?tamano=6  (Bearer admin)  ->  total=23
aud_cod | aud_usu | aud_accion | aud_recurso                | aud_resultado
   23   |    1    | LOGIN      | /api/v2/auth/login         | 200
   22   |    1    | DELETE     | /api/v2/acceso/usuarios/5  | 200
   21   |    1    | LOGIN      | /api/v2/auth/login         | 200
   20   |    5    | GET        | /api/v2/sistema/configuracion | 403
   19   |    5    | LOGIN      | /api/v2/auth/login         | 200
   18   |  NULL   | LOGIN_FAIL | /api/v2/auth/login         | 401
```
**Vista**: pestaña "Registro de auditoría" en `Configuracion.jsx` (misma consulta, renderizada en tabla).

---

## 2. Prueba 403 (S1-16)

Usuario con rol **Operador** (permisos `datos:leer, deteccion:leer, modelo:leer, nodos:leer, tablero:leer`),
intentando una ruta de administración:
```
GET /api/v2/sistema/configuracion  ->  HTTP 403
{"detail":"No tiene el permiso sistema:leer"}
```

## 3. Prueba 429 (S1-17)

### 3.1 Por bloqueo de intentos (S1-7) — ver 1.3.
### 3.2 Por límite de peticiones (S1-15), con `V2_RATE_LIMIT_MAX=5` en modo demo:
```
peticion 1 -> 200
peticion 2 -> 200
peticion 3 -> 200
peticion 4 -> 200
peticion 5 -> 200
peticion 6 -> 429
peticion 7 -> 429
peticion 8 -> 429
peticion 9 -> 429
```

---

## 4. Protección de rutas internas y de los datos (S1-18, S1-19)

### 4.1 Rutas internas cerradas (S1-18)

Antes, `/telemetria/push`, `/telemetria/actual` y `/estado/conexiones` respondían a cualquiera. Ahora cada
una exige la credencial que le corresponde según quién la llama:

| Ruta | Quién la llama | Control | Sin credencial | Con credencial |
|---|---|---|---|---|
| `POST /telemetria/push` | recolector (servicio interno) | cabecera `X-Internal-Token` (= `V2_INTERNAL_TOKEN`) | `401 {"detail":"Token interno inválido."}` | pasa la puerta (cuerpo inválido → `422`) |
| `GET /telemetria/actual` | frontend (dashboard) | JWT de usuario | `401 {"detail":"Falta el token de acceso"}` | `200` (`nodo=Servidor Negocio`) |
| `GET /estado/conexiones` | frontend (`Configuracion.jsx`) | permiso `sistema:leer` | `401` | `200` (`monitored.conectado=true`) |

Salida real de la corrida:
```
/api/v2/telemetria/actual SIN token -> HTTP 401
/api/v2/estado/conexiones SIN token -> HTTP 401
/telemetria/push SIN X-Internal-Token -> HTTP 401
/telemetria/push CON token -> HTTP 422 (pasa la puerta; falla el cuerpo)
/api/v2/telemetria/actual CON token -> 200
/api/v2/estado/conexiones CON token -> 200
```

**Nota de implementación (desviación honesta del plan).** El plan pedía `INTERNAL_TOKEN` en las tres rutas,
pero dos de ellas las llama el **navegador** (dashboard y pantalla de configuración), que no puede guardar
un secreto compartido. Por eso:
- `/telemetria/push` (solo la llama el recolector) usa `X-Internal-Token`;
- `/telemetria/actual` y `/estado/conexiones` piden **sesión de usuario**; la segunda además con el permiso
  `sistema:leer`, porque es información de administración.

El recolector (`collector/stream.py`) ya manda la cabecera: `_cabeceras()` la agrega siempre, leyendo
`STREAM_INTERNAL_TOKEN` (`config.py`), que por defecto **reutiliza** `V2_INTERNAL_TOKEN` del `backend/.env`
(el mismo secreto, sin duplicarlo). Comprobado: el recolector arma la cabecera y su valor coincide con el
del backend.

Los intentos contra la ruta interna **quedan auditados** (el middleware registra toda escritura):
```
aud_cod=28  aud_usu=NULL  aud_accion=POST  aud_recurso=/api/v2/telemetria/push  aud_resultado=401
aud_cod=29  aud_usu=NULL  aud_accion=POST  aud_recurso=/api/v2/telemetria/push  aud_resultado=422
```

Nota: existían **dos** rutas para lo mismo, `GET /sistema/conexiones` (ya pedía `sistema:leer`) y
`GET /estado/conexiones` (abierta, y era la que usaba la pantalla de configuración). Ahora las dos exigen
`sistema:leer`, así que el estado del servidor monitoreado ya no se ve sin sesión ni sin permiso.

### 4.2 Enmascarado del SQL crudo (S1-19)

`enmascarar_sql()` (`backend/app/v2/services/privacidad.py`) reemplaza los literales sensibles por `***`
**al responder la API**: la fila original queda intacta en la base (para el análisis forense). Se aplica en
`EventoOut`, el schema de `/datos/eventos`, es decir en el único punto por el que `eve_sql` sale al navegador.

Reglas: literales de texto (`'...'` / `N'...'`), números de tarjeta, correos, cadenas de 6+ dígitos
(DNI/RUC/teléfono/cuentas), valores ligados (`@P1=16002`) y valores numéricos comparados (`saldo=15000`).

Prueba con el **SQL real capturado** por el recolector (Extended Events, `training/output/anomalias/...`):
```
crudo -> declare @p1 int set @p1=16002 exec sp_prepexec @p1 output,N'@P1 nvarchar(112),@P2 nvarchar(112)...'
mask  -> declare @p1 int set @p1=*** exec sp_prepexec @p1 output,'***','***','***','***',NULL,NULL,'***' select @p1
```

Prueba por el camino de la API (FastAPI serializa la fila con `EventoOut`):
```
antes -> SELECT * FROM cliente WHERE dni='45123456' AND correo='juan.perez@gmail.com' AND saldo=15000
API   -> SELECT * FROM cliente WHERE dni='***' AND correo='***' AND saldo= ***
```

**Aclaración honesta:** la base demo **no** trae datos de clientes en `eventos` (sus 360 textos son mensajes
como "Tiempo de espera agotado al esperar un bloqueo (tabla ventas)"), así que las pruebas de arriba usan un
SQL real de la captura del recolector y un caso de ejemplo. No se afirma que la base contenga datos personales.

---

## 5. CORS restringido y cabeceras de seguridad (S1-9, S1-10)

### 5.1 CORS (S1-9)

Antes: `allow_origins=["*"]` (cualquier web podía llamar a la API). Ahora solo los orígenes reales del
proyecto (`V2_CORS_ORIGINS`): `http://localhost:5173`, `http://127.0.0.1:5173` (Vite) y
`http://localhost:3000`, `http://127.0.0.1:3000` (servidor Node). Fuera de la lista, el navegador ya no
puede leer la respuesta.

```
preflight OPTIONS  http://localhost:5173   -> HTTP 200  Allow-Origin: http://localhost:5173
preflight OPTIONS  http://127.0.0.1:5173   -> HTTP 200  Allow-Origin: http://127.0.0.1:5173
preflight OPTIONS  http://localhost:3000   -> HTTP 200  Allow-Origin: http://localhost:3000
preflight OPTIONS  http://evil.example.com -> HTTP 400  Disallowed CORS origin
GET /salud  Origin: http://127.0.0.1:5173  -> HTTP 200  Allow-Origin: http://127.0.0.1:5173
GET /salud  Origin: http://evil.example.com -> HTTP 200  SIN Allow-Origin (el navegador bloquea la lectura)
```

El front no se rompe: en desarrollo llama por el proxy de Vite (`/api/v2`, mismo origen) y en producción el
servidor Node sirve el front y hace de proxy; en ninguno de los dos casos hay CORS de por medio.

### 5.2 Cabeceras de seguridad (S1-10)

Middleware `app/v2/cabeceras.py` (`poner_cabeceras`), registrado **por fuera** de los demás para que
también las lleven las respuestas de error:

```
orden externo -> interno: poner_cabeceras · auditar_peticion · CORSMiddleware · limitar_peticion

GET /api/v2/salud -> HTTP 200        GET /api/v2/telemetria/actual -> HTTP 401
   X-Content-Type-Options: nosniff      X-Content-Type-Options: nosniff
   X-Frame-Options: DENY                X-Frame-Options: DENY
   Referrer-Policy: no-referrer         Referrer-Policy: no-referrer
```

---

## 6. Escaneo de dependencias y de superficie (S1-14)

**Nota honesta de alcance:** OWASP ZAP **no** está instalado en el equipo (tampoco Docker), así que no hay
reporte de ZAP. En su lugar se corrió `npm audit` sobre el frontend y un escaneo básico hecho con el propio
entorno (`docs/escaneos/escaneo_api.py`, sin dependencias nuevas). Los reportes crudos quedan en
`docs/escaneos/`.

### 6.1 Dependencias del frontend (`npm audit`, 2026-10-14)

```
$ npm audit --audit-level=low
found 0 vulnerabilities        (info 0 · low 0 · moderate 0 · high 0 · critical 0)
```
Reportes: `docs/escaneos/npm_audit_frontend_2026-10-14.txt` y `.json`.

Backend (Python): `pip check` → `No broken requirements found.` (solo coherencia de dependencias; **no** es
una auditoría de CVEs, `pip-audit` no está instalado). Reporte: `docs/escaneos/pip_check_backend_2026-10-14.txt`.

### 6.2 Superficie de la API y del front (escaneo básico)

```
GET /api/v2/salud        -> 200   Server: uvicorn · X-Powered-By: ausente
                                  X-Content-Type-Options: nosniff · X-Frame-Options: DENY · Referrer-Policy: no-referrer
TRACE /api/v2/salud      -> 405   {"detail":"Method Not Allowed"}
DELETE /api/v2/salud     -> 405   {"detail":"Method Not Allowed"}
GET /docs, /redoc, /openapi.json -> 200 sin sesión            (ver H2)
GET /.env (Vite 5173)    -> 403 Restricted
GET /.git/config (Vite)  -> 200 pero devuelve el index.html del SPA (no hay carpeta .git)
GET /package.json (Vite) -> 200 application/json (el package.json real; solo en el servidor de desarrollo)
GET /src/services/api.js -> 200 (fuente servida; normal en el servidor de desarrollo)
GET /api/v2/telemetria/actual sin token -> 401 {"detail":"Falta el token de acceso"}
POST /api/v2/telemetria/push sin token  -> 401 {"detail":"Token interno inválido."}
GET /api/v2/salud con Origin http://evil.example.com -> 200 pero SIN Access-Control-Allow-Origin
Servidor Node (3000): no estaba levantado en la corrida -> no se escaneó
```

**Hallazgos**

| # | Hallazgo | Estado |
|---|---|---|
| H1 | `Server: uvicorn` revela el servidor (huella). Impacto bajo. | Aceptado (se puede ocultar en el proxy) |
| H2 | `/docs`, `/redoc` y `/openapi.json` son públicos: cualquiera ve el mapa de endpoints y los esquemas. | **Decisión consciente**: se deja para la demostración/sustentación; en producción se cierra (`FastAPI(docs_url=None, redoc_url=None)`) o se pone detrás del proxy con sesión |
| H3 | El **servidor de desarrollo** de Vite sirve `/package.json` y los fuentes (`/src/...`). Es lo normal en Vite; en producción el front lo sirve Node con el `dist` compilado. `.env` sí queda bloqueado (403). | Aceptado (solo entorno de desarrollo) |
| H4 | El `index.html` declara `lang="en"` (idioma/accesibilidad). | Pendiente → **S2-5** |

Lo que **no** apareció: inyección SQL (el backend usa el ORM con parámetros ligados en todo el v2), rutas
internas abiertas (cerradas en S1-18) ni CORS abierto (restringido en S1-9); tampoco dependencias
vulnerables en el frontend.

---

## 7. Protección CSRF por doble-envío (S1-8)

**Decisión (actualizada 2026-10-15):** se **implementa** la protección CSRF por **doble-envío** (cookie +
cabecera) como **defensa en profundidad**.

**Razón técnica:** la protección CSRF existe porque el navegador adjunta las cookies por su cuenta, incluso
desde otro sitio. Aquí la v2 **no usa cookies de sesión**: el JWT viaja en `Authorization: Bearer` y el
frontend lo guarda **solo en memoria** (ni `localStorage` ni `sessionStorage`), así que una web ajena no puede
leer el token ni hacer que el navegador lo adjunte. Por eso la superficie clásica de CSRF no existe y el
control es **redundante hoy**; se deja implementado y probado para el caso de que las credenciales pasaran a
cookies (p. ej. un *refresh token*).

**Cómo funciona** (`backend/app/v2/csrf.py`, registrado en `backend/app/v2/main.py`):

1. La API emite una cookie `csrf_token` (legible por JS, `SameSite=Lax`) con un valor aleatorio por navegador
   si aún no existe.
2. En cada escritura (`POST`/`PUT`/`PATCH`/`DELETE`) de `/api/v2` se exige la cabecera `X-CSRF-Token` con el
   mismo valor. Si falta o no coincide → **403** (`{"detail": "Token CSRF ausente o invalido."}`).

El frontend (`frontend/src/services/api.js`) lee la cookie y agrega la cabecera en cada escritura. El proxy
Node **ya no elimina** la cabecera `cookie` (`frontend/server/proxy.js`), para que la cookie llegue a FastAPI.

**Exenciones:** `GET`/`HEAD`/`OPTIONS` (no cambian datos); `POST /auth/login` (aún no hay cookie); y las rutas
internas del recolector/Node (`/telemetria/push` e `/internal/*`), que llegan con `X-Internal-Token`.

**Orden de middlewares:** `proteger_csrf` va por dentro de `auditar_peticion`, de modo que un 403 por CSRF
**también queda auditado**; y `poner_cabeceras` por fuera, para que el 403 lleve las cabeceras de seguridad.

**Comprobación (ejecutada contra la API viva):**

```
GET  /api/v2/salud                               -> 200  (emite Set-Cookie: csrf_token=...)
POST /api/v2/auth/logout   (solo cookie)          -> 403  Token CSRF ausente o invalido
POST /api/v2/auth/logout   (X-CSRF-Token: malo)   -> 403  Token CSRF ausente o invalido
POST /api/v2/auth/logout   (cookie + token)       -> 401  Falta el token de acceso   (pasa CSRF; falla por falta de JWT)
POST /api/v2/auth/login    (exento)               -> 401  Usuario o clave incorrectos  (llega a la lógica de login)
```

El 403 del CSRF se registra igualmente: el middleware de auditoría cubre toda escritura y todo 403 de
`/api/v2`, así que la fila queda en `dbo.auditoria` con resultado 403.

---

## 8. Saneamiento de secretos, SQL solo-lectura y HTTPS (S1-11, S1-12, S1-13)

### 8.1 .gitignore raíz y secretos (S1-11)

Se añadió `.gitignore` en la **raíz** del repositorio con exclusiones para:
- Archivos `.env` (y variantes) en cualquier nivel: `.env`, `.env.*`, `**/.env`, `**/.env.*`
- Salidas del recolector/modelado: `backend/app/tools/output/`, `training/output/`, `*.parquet`, `*.joblib`, `*.pkl`, etc.
- Reportes de escaneo generados localmente (`docs/escaneos/*.json`, `docs/escaneos/*.txt`) dejando solo el script reproducible
- Certificados/llaves: `*.key`, `*.pem`, `*.crt`, `*.pfx`

`backend/.env.example` se actualizó para **no contener valores reales** (usa placeholders como `CAMBIAR_*`). `frontend/.env.example` (servidor Node) ya existía y se referencia; no se añadieron secretos.

**Nota:** no se eliminaron `.env` existentes del disco (no se borra nada sin aprobación). Simplemente quedan excluidos de futuros commits.

### 8.2 Usuario SQL de solo lectura (S1-12)

Script preparado (sin aplicar): `docs/scripts_sql/login_lectura_steelnort_monitor.sql`

Qué hace (idempotente):
- Crea (o actualiza contraseña de) el login SQL `steelnort_monitor` (Autenticación SQL).
- Mapea a `SteelNort` → rol `db_datareader` (solo lectura).
- Mapea a `bdSteelNort_v4` → rol `db_datareader` (solo lectura).

Recomendación de aplicación (tras aprobarlo en BD):
```sql
-- Ejecutar con sysadmin en SQL Server
:r "D:\SteelNort_web_v2\docs\scripts_sql\login_lectura_steelnort_monitor.sql"
```

Tras aplicarlo, el recolector debe usar `SQL_USER=steelnort_monitor` con una contraseña distinta a `sa`. En `backend/.env.example` ya aparece esa configuración por defecto (`SQL_USER=steelnort_monitor`).

**Privilegios mínimos:** únicamente `db_datareader` en ambas bases. No tiene escritura, ni DDL, ni EXEC de procedimientos administrativos.

### 8.3 HTTPS/TLS documentado (S1-13)

Se documentó la configuración para poner TLS delante de la API/frontend: `docs/Configuracion_TLS.md`

- **Arquitectura recomendada:** Nginx (o Apache) como **reverse proxy** con HTTPS (Let's Encrypt). El backend FastAPI sigue en HTTP interno (8200) y el proxy termina TLS.
- **Alternativa de prueba:** Uvicorn con `--ssl-keyfile/--ssl-certfile` (solo para pruebas locales).
- **Certificados:** nunca se versionan (están en `.gitignore`). Se recomienda HSTS en el proxy.
- **Coherente con lo ya hecho:** CORS + cabeceras de seguridad siguen aplicando; el JWT viaja cifrado por HTTPS.

**Conclusión:** HTTPS queda **documentado y listo para habilitar** en producción/demo real. No se aplicó en el entorno actual (HTTP en localhost) para no romper el flujo de desarrollo ya verificado.

## 9. Estado del entorno tras las pruebas

- Backend y Vite **quedaron levantados** con la configuración normal (límite 2000/min).
- La cuenta temporal `qa_auditoria` (usu_cod=5) quedó **dada de baja** (`usu_est='I'`). No se puede
  borrar físicamente porque `dbo.auditoria.aud_usu` la referencia (FK): el registro de auditoría
  protege la integridad del historial. Sus contadores quedaron en 0.
- Filas `aud_cod=1..2` son del primer prototipo del middleware (antes de que el login se registrara
  con acción semántica); se conservan porque **el registro de auditoría no se borra**.

## 9. Reproducir

```powershell
# Backend
cd D:\SteelNort_web_v2\backend; $env:PYTHONUTF8=1
& .\.venv\Scripts\python.exe -m uvicorn app.v2.main:app --host 127.0.0.1 --port 8200
# Frontend
cd D:\SteelNort_web_v2\frontend; npm run dev
# Migraciones (idempotentes)
sqlcmd -S localhost -d bdSteelNort_v4 -E -C -b -i D:\SteelNort_web_v2\database\migracion_auditoria.sql
sqlcmd -S localhost -d bdSteelNort_v4 -E -C -b -i D:\SteelNort_web_v2\database\migracion_intentos_bloqueo.sql
```
