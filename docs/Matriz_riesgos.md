# Matriz de riesgos y amenazas — Sistema de anomalías v2 (Steel Nort)

**Fecha:** 2026-10-13 (actualizada 2026-10-15)
**Alcance:** backend v2 (FastAPI), frontend (React/Vite), recolector de métricas y base `bdSteelNort_v4`.
**Uso:** evidencia del criterio **Protección** (control de uso indebido) y apoyo a **Seguridad**. Cada riesgo tiene su estado honesto: *Mitigado*, *Parcial* o *Pendiente* (con la tarea del plan que lo cierra).

> Metodología: probabilidad (P) e impacto (I) en escala Baja/Media/Alta. El nivel es el producto cualitativo.

| # | Amenaza / escenario adverso | P | I | Nivel | Control actual | Estado | Tarea que lo cierra |
|---|---|---|---|---|---|---|---|
| R1 | **Robo de token JWT** (XSS o equipo compartido) y suplantación de un administrador | Media | Alto | Alto | JWT firmado; el token vive en memoria (no en `localStorage`); caducidad corta; CORS restringido (S1-9) y cabeceras `nosniff`/`DENY`/`no-referrer` (S1-10). CSRF por doble-envío como defensa en profundidad (S1-8) | Parcial | S1-13 (HTTPS) y S2-5 (evitar XSS en la interfaz) |
| R2 | **Fuerza bruta contra `/auth/login`** | Alta | Medio | Alto | Bloqueo por intentos: tras 5 fallos la cuenta responde 429 (`Retry-After`); un login correcto limpia el contador; el límite por IP añade otra capa | **Mitigado (2026-10-13)** | — (evidencia en `docs/Evidencia_seguridad.md` §1.3 y §3) |
| R3 | **Inyección SQL** por parámetros de filtro/listado | Baja | Alto | Medio | SQLAlchemy ORM con parámetros ligados en todo el backend v2; sin concatenación de SQL de usuario | Mitigado | — (vigilar `text()` puntuales) |
| R4 | **Abuso/DoS de la API** (ráfaga legítima o maliciosa) | Media | Medio | Medio | Límite de peticiones por IP en FastAPI (429) + rate limit del proxy Node | **Mitigado (2026-10-13)** | — (evidencia en `docs/Evidencia_seguridad.md` §3.2) |
| R5 | **Acceso a endpoints internos sin autenticación** (`/telemetria/push`, `/telemetria/actual`, `/estado/conexiones`) | Media | Medio | Medio | `/telemetria/push` exige `X-Internal-Token`; `/telemetria/actual` exige JWT; `/estado/conexiones` exige `sistema:leer`; los intentos fallidos quedan auditados | **Mitigado (2026-10-14)** | — (evidencia en `docs/Evidencia_seguridad.md` §4.1) |
| R6 | **Credenciales versionadas** (`backend/.env`, `frontend/.env`, usuario `sa` con contraseña en `collector/config.py`) | Alta | Alto | Alto | Sin `.gitignore` raíz; secretos en el repo | Pendiente | **S1-11** (sanear + rotar) + **S1-12** (usuario SQL solo-lectura) |
| R7 | **Fuga de datos sensibles por los logs SQL** (`sql_text` crudo con literales de clientes) | Media | Alto | Alto | `enmascarar_sql()` en `EventoOut`: el navegador recibe el SQL con los literales en `***`; la base conserva el original para el análisis forense. Marco legal y alcance en `Indicadores_v2.md` → «Protección de datos personales (Ley N.° 29733)» | **Mitigado (2026-10-14)** | — (evidencia en `docs/Evidencia_seguridad.md` §4.2 y §5) |
| R8 | **Sobrecarga del recolector** (degrada el OLTP monitoreado) | Baja | Medio | Bajo | Recolector aparte; sin medición de su consumo publicada | Parcial | S3 (medir consumo del recolector) |
| R9 | **Contaminación del baseline** (datos de una corrida anómala entran al entrenamiento) | Media | Alto | Alto | Guardas de volumen (`MAX_MUESTRAS` 1000, `DIAS_MAXIMOS` 30) y `origen.json` con `es_carga_normal`; el reentrenamiento es event-driven | Parcial | Documentar la guarda; no hay validación automática del baseline → riesgo declarado |
| R10 | **Fatiga de alarmas** (demasiadas alertas y el operador deja de mirarlas) | Media | Medio | Medio | Histéresis + consenso N-de-M + anti-flap (`DecisorZonal`); severidad por reglas | Parcial | S3 (ajuste fino con umbrales configurables) |
| R11 | **Caída de la fuente monitoreada** (SQL Server objetivo no responde) | Media | Medio | Medio | `/estado/conexiones` y `/api/v2/salud` informan sin lanzar excepción; spool JSONL en el collector | Parcial | S2-12 (pruebas de falla + evidencia) |
| R12 | **Código muerto / confianza falsa** (controles de seguridad que se anuncian pero no se usan) | Baja | Bajo | Bajo | CSRF **implementado y en uso**: middleware `app/v2/csrf.py` (doble-envío) con 403 real ante token ausente/inválido, y el frontend envía `X-CSRF-Token`. No queda código CSRF sin usar | **Mitigado (2026-10-15)** | — (evidencia en `docs/Evidencia_seguridad.md` §7) |
| R13 | **Falta de trazabilidad** ("¿quién cambió este umbral?") | Alta | Medio | Alto | Antes: solo columnas `reg_usu/fec_reg` por fila, sin historial de acciones | **Mitigado (2026-10-13)** | S1-1…S1-5 (tabla `auditoria` + endpoint + vista) |
| R14 | **API consumible desde cualquier web** (CORS `*`) | Media | Medio | Medio | Antes `allow_origins=["*"]`. Ahora solo los orígenes del proyecto (Vite 5173 / Node 3000, local y 127.0.0.1); un origen ajeno recibe `Disallowed CORS origin` y sin `Access-Control-Allow-Origin` el navegador no lee la respuesta | **Mitigado (2026-10-14)** | — (evidencia en `docs/Evidencia_seguridad.md` §5.1) |
| R15 | **Dependencias de terceros con vulnerabilidades conocidas** (frontend npm, backend Python) | Media | Alto | Alto | `npm audit` del frontend: **0 vulnerabilidades** (info/low/moderate/high/critical = 0); `pip check` del backend sin conflictos | Parcial | — frontend cerrado (`Evidencia_seguridad.md` §6.1); falta auditar CVEs del backend (`pip-audit` no instalado) |
| R16 | **Documentación de la API expuesta sin sesión** (`/docs`, `/redoc`, `/openapi.json`) | Baja | Bajo | Bajo | No expone datos, solo el mapa de endpoints y los esquemas. Se deja pública a propósito para la demostración/sustentación | Aceptado conscientemente | Cerrar en producción con `FastAPI(docs_url=None, redoc_url=None)` o detrás del proxy con sesión (ya documentado) |
| R17 | **CSRF** (que una web ajena fuerce una escritura autenticada desde el navegador de la víctima) | Baja | Alto | Medio | En este diseño no hay cookies de sesión (JWT en memoria), así que la superficie clásica no existe; además, control de **doble-envío** (`csrf_token` + `X-CSRF-Token`, 403 si no coinciden) en todas las escrituras de `/api/v2` (S1-8) | **Mitigado (2026-10-15)** | — (evidencia en `docs/Evidencia_seguridad.md` §7) |

## 1. Riesgos aceptados conscientemente

- **R8** y **R9**: se documentan como limitaciones conocidas en la demo; no se cierran en el alcance actual.
- **R16**: la documentación de la API (`/docs`, `/redoc`, `/openapi.json`) queda pública **a propósito** para la
  demostración y la sustentación. No expone datos, solo el mapa de endpoints y los esquemas; en producción se
  cierra con `docs_url=None`/`redoc_url=None` o detrás del proxy con sesión.
- **R13** era el riesgo que más afectaba al criterio de Protección y ya quedó cerrado.

## 2. Trazabilidad con el plan

- Cierres inmediatos (Sprint 1): R2, R4, R5, R6, R7, R12, R13, R14, R15.
- Cierres del Sprint 2/3: R1 (parcial), R11, R10, R8.

> **Honestidad:** los riesgos *Pendiente* se declaran como tales en la sustentación. Es mejor
> presentar la matriz con su estado real que afirmar controles que el código no tiene.
