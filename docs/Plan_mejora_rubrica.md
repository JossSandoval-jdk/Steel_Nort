# Plan de mejora para maximizar la rúbrica de producto (14 pts)

**Proyecto:** Sistema inteligente con aprendizaje automático para observabilidad y diagnóstico de anomalías de rendimiento en el OLTP de Steel Nort
**Fecha:** 2026-10-13
**Punto de partida (auditoría estática):** ~7.9 / 14 (≈56 %)
**Meta realista:** 12.5 – 13.5 / 14
**Entregas:** 16 oct (90 %), 20 oct (evidencias de seguridad/fiabilidad), 23 oct (100 %)

> Regla de la rúbrica: para acercarse al tope de un nivel hay que cumplir **todas** las viñetas del nivel "Bueno" de forma demostrable en vivo. Este plan ataca en ese orden.

---

## 1. Principios del plan

- **Todo aditivo.** No se borra ni reemplaza nada existente sin aprobación.
- **Sin dependencias nuevas** (salvo herramientas externas de medición, que no se instalan como paquete del proyecto).
- **Código simple y con comentarios puntuales**, siguiendo el estilo actual.
- **Datos honestos.** No se publica ninguna cifra que no esté respaldada por un artefacto del repo.
- **Cada tarea produce evidencia** demostrable en la demo (captura, JSON, log o documento).

---

## 2. Prioridad global (puntos ganados / esfuerzo)

Los criterios gordos son **Interacción (2.5) + Seguridad (2.5) + Protección (2.5) = 7.5 de 14**. Ahí está el 54 % del puntaje.

| Sprint | Foco | Criterios | Meta de puntaje |
|---|---|---|---|
| **S0** | Honestidad y base documental (barato) | Todas | evita restas / +0.3 |
| **S1** | Seguridad + Protección (5 pts) | Seguridad, Protección | +1.6 |
| **S2** | Interacción (2.5 pts) + Fiabilidad | Interacción, Fiabilidad | +1.3 |
| **S3** | Eficiencia + Flexibilidad + Adecuación | Eficiencia, Flexibilidad, Adecuación | +1.4 |

---

## 3. Sprint 0 — Honestidad y base (antes del 16 oct)

| ID | Acción | Entregable | Esfuerzo |
|---|---|---|---|
| S0-1 | Corregir las cifras de `docs/Evaluacion_producto.md:65`: quitar **F1 0.982 / FPR 4.8 %** (sin respaldo: prueba con 108 ventanas pre-seleccionadas) y usar **F1 0.964 / recall 100 % / FPR ventana 2.74 %** (normalizado q01, `honesto.json`). | doc corregido | 15 min |
| S0-2 | Marcar `metrics.json` y `freeze.json` como **legacy** (dicen `ENSEMBLE_Z`); dejar claro que la fuente válida es `honesto.json`. | nota en doc | 15 min |
| S0-3 | No afirmar "operaciones principales 0.2–0.5 s" hasta tener la tabla medida (S3-1). | doc corregido | 10 min |
| S0-4 | Documento de **alineación de RF10** (gestión de usuarios): justificar por qué está y no estaba en RF1–RF7, o anexarlo al proyecto aprobado. | `docs/Alineacion_RF.md` | 30 min |
| S0-5 | Rellenar la **matriz de evidencias** de `Evaluacion_producto.md` §6 con lo ya existente (health check, TTFA, métricas del modelo). | doc actualizado | 30 min |

---

## 4. Sprint 1 — Seguridad y Protección (+1.6 pts)

### 4.1 Registro de auditoría (la viñeta que define el nivel Bueno en Seguridad)

| ID | Acción | Detalle técnico | Entregable |
|---|---|---|---|
| S1-1 | Tabla `auditoria` | `aud_cod, aud_usu, aud_accion (método HTTP), aud_recurso, aud_resultado, aud_ip, aud_fec` | `database/migracion_auditoria.sql` ✅ **hecho** |
| S1-2 | Modelo + servicio | `models/sistema.py` (`Auditoria`) + `services/auditoria.py` (`listar()`) | código ✅ **hecho** |
| S1-3 | Enganches | **Middleware transversal** `app/v2/auditoria.py`: registra toda petición POST/PUT/PATCH/DELETE sobre `/api/v2` con su código de resultado (cubre login fallido, 403 y 409 sin tocar cada servicio) | código ✅ **hecho** |
| S1-4 | Endpoint | `GET /api/v2/sistema/auditoria` con permiso `sistema:leer` (filtros por usuario/acción/recurso) | `routers/sistema.py` ✅ **hecho** |
| S1-5 | Vista en UI | Columna "Registro de auditoría" en `Configuracion.jsx` (usuario, acción, recurso, resultado, fecha) | UI ✅ **hecho** |
| S1-6 | Evidencia | Captura respondiendo "¿quién cambió este umbral y cuándo?" | ✅ **hecho** (`docs/Evidencia_seguridad.md` §1) |

### 4.2 Endurecimiento de seguridad

| ID | Acción | Detalle | Entregable |
|---|---|---|---|
| S1-7 | **Bloqueo por intentos fallidos** | Contador en `usuario` (`usu_intentos`, `usu_bloqueo_hasta`); tras N fallos, bloqueo temporal (429); registrar en auditoría | código ✅ **hecho** (`services/acceso.py`, config `login_max_intentos`/`login_bloqueo_minutos`) |
| S1-8 | **CSRF (doble-envío)** | **Implementado** como defensa en profundidad: middleware `app/v2/csrf.py` (cookie `csrf_token` + cabecera `X-CSRF-Token`), exento en el login y en las rutas internas; el frontend la envía desde `services/api.js`. La v2 no usa cookies de sesión (JWT en memoria), por lo que el control es redundante hoy, pero queda probado para un futuro paso a cookies | `app/v2/csrf.py` + `main.py` ✅ **hecho** (`Evidencia_seguridad.md` §7) |
| S1-9 | **CORS restringido** | En `main.py`, `allow_origins` sale de `settings.lista_cors` (`V2_CORS_ORIGINS`): solo Vite (5173) y Node (3000), local y 127.0.0.1. Un origen ajeno recibe `Disallowed CORS origin` | `app/v2/config.py` + `main.py` ✅ **hecho** (`Evidencia_seguridad.md` §5.1) |
| S1-10 | **Cabeceras de seguridad en FastAPI** | Middleware `app/v2/cabeceras.py` con `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` y `Referrer-Policy: no-referrer`, registrado por fuera de los demás (también en 401/403/429) | `app/v2/cabeceras.py` ✅ **hecho** (§5.2) |
| S1-11 | **Sanear secretos** | `.gitignore` raíz que excluya `.env`; dejar solo `.env.example` sin valores reales. Preparado/aplicado: `.gitignore` en raíz + `backend/.env.example` saneado. | config ✅ **hecho** (`Evidencia_seguridad.md` §8.1) |
| S1-12 | **Usuario SQL de solo lectura** | Script SQL para login `steelnort_monitor` con `db_datareader` mínimo en `SteelNort` y `bdSteelNort_v4`. **Preparado sin aplicar** (espera aprobación para ejecutar en SQL Server). | SQL preparado ✅ **hecho** (`docs/scripts_sql/login_lectura_steelnort_monitor.sql`, §8.2) |
| S1-13 | **HTTPS** | Documentación de terminación TLS (Nginx o `uvicorn --ssl-*`) lista para demo, sin tocar certificados ni secretos. | doc ✅ **hecho** (`docs/Configuracion_TLS.md`, §8.3) |
| S1-14 | **Escaneo** | `npm audit` en el frontend (**0 vulnerabilidades**) y escaneo básico de superficie con el propio entorno (`docs/escaneos/escaneo_api.py`). **Nota honesta:** OWASP ZAP y Docker no están instalados, así que no hay reporte de ZAP; el escaneo propio no lo sustituye | `docs/escaneos/` ✅ **hecho** (`Evidencia_seguridad.md` §6) |

### 4.3 Protección (control de uso indebido y riesgos)

| ID | Acción | Detalle | Entregable |
|---|---|---|---|
| S1-15 | **429 real en FastAPI** | Middleware de límite por IP en memoria (sin dependencias nuevas) usando las configs `rate_limit_max` ya existentes | `app/v2/limites.py` ✅ **hecho** |
| S1-16 | **Prueba 403** | Usuario con rol sin permiso intenta gestionar usuarios/cambiar umbral → captura del 403 | ✅ **hecho** (`docs/Evidencia_seguridad.md` §2) |
| S1-17 | **Prueba 429** | Ráfaga de peticiones → captura del 429 | ✅ **hecho** (`docs/Evidencia_seguridad.md` §3) |
| S1-18 | **Proteger endpoints abiertos** | `/telemetria/push` exige `X-Internal-Token`; `/telemetria/actual` exige JWT de usuario; `/estado/conexiones` exige permiso `sistema:leer`. **Desviación honesta:** el plan pedía token interno en las tres, pero dos las llama el navegador (no puede guardar un secreto) | código ✅ **hecho** (`routers/telemetria.py`, `routers/estado.py`, `collector/stream.py`; ver `Evidencia_seguridad.md` §4.1) |
| S1-19 | **Enmascarar `sql_text`** | Función `enmascarar_sql()` (literales, correos, tarjetas, DNI/RUC, `@var=valor`) aplicada en `EventoOut` antes de responder (hoy se veía crudo en `Reportes.jsx:307`); la fila original queda intacta en la base | `services/privacidad.py` + `schemas/datos.py` ✅ **hecho** (§4.2) |
| S1-20 | **Ley 29733** | Sección "Protección de datos personales (Ley N.° 29733)" en el doc técnico: principios, controles que los cumplen y alcance honesto (salvaguarda técnica, no procedimiento legal) | `docs/Indicadores_v2.md` ✅ **hecho** |
| S1-21 | **Matriz de riesgos/amenazas** | Anexo con todos los escenarios adversos (robo de token, SQLi, abuso API, sobrecarga recolector, baseline contaminado, fatiga de alarmas, fuga de datos, caída de la fuente) | `docs/Matriz_riesgos.md` ✅ **hecho** |

---

## 5. Sprint 2 — Interacción (+1.3 pts) y Fiabilidad

### 5.1 Interacción (el criterio más pesado)

| ID | Acción | Detalle | Entregable |
|---|---|---|---|
| S2-1 | **Manual de usuario** (RNF5) | Cómo iniciar sesión, leer el dashboard, entender una alerta, navegar el diagnóstico, generar y exportar un reporte | `docs/Manual_usuario.md` |
| S2-2 | **Encuesta de satisfacción** (≥ 80 %) | Instrumento + aplicación a gerente, encargado de TI y administrador + resultados | `docs/Encuesta_satisfaccion.md` + resultados |
| S2-3 | **Tooltips/ayuda contextual** | Explicar métricas técnicas (PLE, q01, z-score) con `title` o ayuda en el Dashboard/Alertas | UI |
| S2-4 | **Contraste accesible** | Llevar a ≥ 4.5:1 las pastillas que fallan (`.rol-pill.media` 2.9, `.rol-pill.baja` 3.3, `.rol-pill.critica` 4.2, `.sev-A` 3.45) | CSS |
| S2-5 | **ARIA y diálogos** | `aria-label` en botones-icono, `role="dialog"/aria-modal` en `ModalNotificaciones`/`ModalUsuario`, cierre con `Escape`, `lang="es"` en `index.html` | UI |
| S2-6 | **Focus visible global** | Regla `:focus-visible` global (hoy hay `outline:none` sin reemplazo) | CSS |
| S2-7 | **Decidir componentes huérfanos** | `CorrelacionRaiz.jsx` y `HistoriaSesion.jsx` están sin montar y con datos falsos: o se integran con datos reales o se retiran (con tu aprobación) | decisión + UI |
| S2-8 | **Tarea compleja cronometrada** | Ensayar "encontrar la causa de la anomalía de ayer a las 3 pm" < 2 min sin ayuda | evidencia video/captura |

### 5.2 Fiabilidad

| ID | Acción | Detalle | Entregable |
|---|---|---|---|
| S2-9 | **Fix del bug `"0"`** | En `collector/metrics.py` y `stream.py`: guardar **nulo + campo de estado de error** en vez de `0`/`"0"`/`0.0` al fallar | código |
| S2-10 | **Logs estructurados** | Reemplazar `print` por `logging` en `metrics.py`/`eventos.py` | código |
| S2-11 | **Health check documentado** | `/api/v2/salud` y `/estado/conexiones` ya existen: documentar y mostrar en la demo | doc + captura |
| S2-12 | **Pruebas de falla** | (a) detener el recolector → se reinicia y no pierde datos; (b) SQL Server no responde → estado visible y reconexión; (c) API lenta/fallida → la UI avisa y reintenta | capturas/video |
| S2-13 | **Verificación de conteo** | Comparar nº de registros antes/después de una falla | captura |

---

## 6. Sprint 3 — Eficiencia, Flexibilidad y Adecuación (+1.4 pts)

### 6.1 Eficiencia

| ID | Acción | Detalle | Entregable |
|---|---|---|---|
| S3-1 | **Tabla de tiempos por operación** | Medir login, carga del dashboard, consulta de anomalías, detección→alerta visible y generación de reporte (meta ≤ 3 s; n y p95) | `docs/Tiempos.md` + CSV |
| S3-2 | **Consumo del propio recolector** | Medir CPU/memoria del **proceso** recolector con `psutil.Process()` (hoy solo se mide el host) | gráfico/CSV |
| S3-3 | **Prueba de carga** | k6 (o Locust/JMeter) con usuarios concurrentes sobre endpoints clave; guardar resultados | reporte |
| S3-4 | **Corrida larga** | Dejar el sistema varias horas y verificar estabilidad y coherencia de conteos | log + captura |

### 6.2 Flexibilidad

| ID | Acción | Detalle | Entregable |
|---|---|---|---|
| S3-5 | **Umbral configurable sin código** | Que `detector`/`motor` lean el valor de umbral desde `configuracion_sistema` (BD) y se pueda editar desde `Configuracion.jsx` | código + UI |
| S3-6 | **Reglas R1–R7 configurables** | Mover los umbrales hoy hardcodeados (`motor/reglas.py:53-59`) a configuración (BD/archivo) | código |
| S3-7 | **README raíz** | Arranque, arquitectura, estructura de carpetas | `README.md` |
| S3-8 | **Diagrama de módulos** | Recolector → preparación → modelo → motor de reglas → API → web como componentes separados | figura + doc |
| S3-9 | **Guía de extensión** | Cómo agregar una métrica, una regla nueva o cambiar de modelo (RNF4/RNF6) | `docs/Guia_extension.md` |
| S3-10 | **Demo de cambio en vivo** | Cambiar un umbral desde configuración y mostrar el efecto | evidencia |

### 6.3 Adecuación funcional

| ID | Acción | Detalle | Entregable |
|---|---|---|---|
| S3-11 | **Acta de validación con Steel Nort** | Reunión con gerente y encargado de TI; acta firmada de que responde a necesidades reales | `docs/Acta_validacion.md` |
| S3-12 | **Matriz RF → módulo → prueba → resultado** | Completar con resultados reales (existe como plantilla en `Indicadores_v2.md:332-347`) | doc |
| S3-13 | **Corrida end-to-end registrada** | Dejar una ejecución completa recolector→alerta→dashboard→reporte y guardarla como evidencia | log/capturas |

---

## 7. Sustentación (IND5: 14 pts aparte)

No se puede auditar desde archivos: depende de la preparación. Fortalezas del proyecto: es **muy explicable** (artefactos CRISP-DM, `honesto.json`, trazabilidad).

| ID | Acción | Entregable |
|---|---|---|
| IND5-1 | Explicación de 2 min por módulo (recolector, preparación, modelo, motor de reglas, API, web) | guion |
| IND5-2 | Ensayo con cronómetro de 6 modificaciones típicas (umbral, regla nueva, tarjeta en dashboard, métrica nueva, rol/permiso, filtro de reporte) | guion |
| IND5-3 | Respuestas ensayadas con **conclusión** y enlace al proyecto/pre informe (por qué ese modelo, por qué solo datos normales, fuga de datos, fallas, 3 s, roles/auditoría, limitaciones) | guion |
| IND5-4 | Tener listas las cifras correctas (F1 0.964 / recall 100 % / FPR 2.74 %; TTFA 4.0 s mediana / 8.9 s media) | tarjeta de datos |

---

## 8. Cronograma

| Fecha | Hito | Qué debe estar listo |
|---|---|---|
| **14 oct (hoy)** | Sprint 0 | **Listo** – Cifras corregidas, alineación RF10, matriz de evidencias |
| **14–15 oct** | Sprint 1 | **Avanzado** – Auditoría, bloqueo de intentos, 403/429, CORS+cabeceras, enmascarado de `sql_text`, matriz de riesgos, escaneo, retiro CSRF. **Quedan:** S1-11 (secretos/`.gitignore`), S1-12 (SQL solo-lectura), S1-13 (HTTPS documentado) |
| **16 oct** | 90 % | Flujo completo demostrable + tabla de tiempos (S3-1) |
| **17–20 oct** | Sprint 2 | Manual, encuesta, accesibilidad, fix `"0"`, pruebas de falla |
| **21–23 oct** | Sprint 3 | Prueba de carga, corrida larga, configurabilidad, README/guía, acta |
| **Después** | Ensayo | Sustentación cronometrada |

---

## 9. Checklist final "todas las viñetas Bueno"

Marcar solo cuando sea **demostrable en vivo**:

- [ ] **Adecuación:** RF1–RF7 integrados · capacidades adicionales visibles · resultados exactos · acta Steel Nort · RF10 alineado
- [ ] **Eficiencia:** tabla ≤ 3 s por operación · prueba de carga · consumo del recolector · corrida larga estable
- [ ] **Interacción:** estético · accesible (contraste/teclado/aria) · tarea compleja < 2 min · prevención de errores · retroalimentación · manual + ayuda · encuesta ≥ 80 %
- [ ] **Fiabilidad:** sin fallos visibles · recuperación sin pérdida · fix `"0"` · health check · logs · pruebas de falla
- [ ] **Seguridad:** ✅ JWT · ✅ bcrypt · ✅ bloqueo de intentos · ✅ CORS/cabeceras · ✅ HTTPS documentado · ✅ roles · ✅ **auditoría** · ✅ solo lectura SQL (script preparado) · ✅ secretos fuera del repo
- [ ] **Flexibilidad:** umbral/rReglas configurables · modular documentado · modelo intercambiable · guía de extensión · cambio en vivo
- [ ] **Protección:** ✅ 403 · ✅ 429 · ✅ solo lectura (script preparado) · ✅ enmascarar `sql_text` · ✅ Ley 29733 · ✅ **matriz de riesgos completa**

---

## 10. Riesgos y mitigación

| Riesgo | Mitigación |
|---|---|
| Publicar cifras no respaldadas (0.982 / 4.8 %) | Sprint 0 corrige todo el doc |
| El evaluador pide la tabla de tiempos y no existe | S3-1 antes del 16 oct |
| El bug `"0"` contamina el baseline en la demo | S2-9 antes de cualquier reentrenamiento |
| Endpoints abiertos detectados como agujero | S1-18 ✅ **hecho** (2026-10-14) |
| `window.confirm` para cambiar umbral no existe (no hay UI de umbral) | S3-5 incluye confirmación |
| Tiempo insuficiente para todo antes del 23 oct | Orden por puntos/esfuerzo del §2; mínimo viable = Sprints 0+1+2.1 |
