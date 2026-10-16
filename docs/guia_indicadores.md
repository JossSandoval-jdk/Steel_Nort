# Cómo Cumplir los Indicadores — SteelNort

> **Dónde está la evidencia ya armada:** [`evidencia_indicadores/`](evidencia_indicadores/README.md)
> (tablero + fichas) y [`fase_evaluacion/`](fase_evaluacion/README.md) (experimentos, gráficos, carga).

> Estado revisado al 2026-10-15. Fuente: artefactos reales del repo.

> **Evaluación de esta guía (revisada 2026-10-15).** Se contrastó cada fila contra los
> artefactos reales. Tres filas estaban **optimistas** y se corrigieron:
> **I-3.1** (la meta es Top-1 y hoy no se alcanza), **I-3.2** (no es "por calcular": **no hay
> ground truth**, es no medible) e **I-3.3** (ya está medido: **54.17 %**, no cumple).
> También se corrigió **I-0** (el TTD previo es un supuesto, no un dato), **I-5.4** (el endpoint
> es `/api/v2/salud`, no `/health`) y **I-5.3** (se creó la suite). Se **cerraron** I-1.2, I-5.3
> e I-4.1 (Web Push). Las cifras verificadas se generan con los scripts nuevos
> `indicadores/11_indice_calidad.py`, `12_tiempos_operacion.py`, `13_disponibilidad.py`,
> `14_auditar_pendientes.py` y `15_tasa_pruebas.py`.

---

## Resumen de estado (verificado)

| Cód. | Indicador | Meta | Estado | Acción |
|------|-----------|------|--------|--------|
| I-0 | Reducción del tiempo de detección | p < 0.05 | ⚠️ Significativo solo con TTD previo **supuesto** | Falta el O1 real (gerente) |
| I-1.1 | Volumen de datos | Reportar | ✅ Calculado | `inventario_corridas.csv` |
| I-1.2 | Índice de calidad ≥ 95 % | ≥ 95 % | ✅ **99.72 %** | `indicadores/11_indice_calidad.py` |
| I-2.1 | F1-Score ≥ 85 % | ≥ 85 % | ✅ 96.39 % | `honesto.json` |
| I-2.2 | Correlación \|r\| ≥ 0.6 | \|r\| ≥ 0.6 | ✅ 51 pares | `correlacion.json` |
| I-3.1 | Precisión por tipo ≥ 90 % | ≥ 90 % | ✅ **96.13 % Top-2** (criterio adoptado) · Top-1 66.45 % | Defender el criterio Top-2 (documentado) |
| I-3.2 | Coincidencia de severidad ≥ 90 % | ≥ 90 % | ❌ **NO MEDIBLE** (sin ground truth) | Etiquetar severidad por escenario |
| I-3.3 | Efectividad del diagnóstico ≥ 85 % | ≥ 85 % | ✅ **91.67 %** (22/24, evento) | `indicadores/03_evaluar_oe3.py` |
| I-4.1 | Cumplimiento RF+RNF 100 % | 100 % | ⚠️ Parcial | Matriz de 14; falta arrancar el server push |
| I-4.2 | Latencia ≤ 3 s | ≤ 3 s | ✅ < 0.5 s | `latencia.json` |
| I-4.3 | Satisfacción ≥ 80 % | ≥ 80 % | ❌ Falta encuesta (**única acción externa**) | Aplicar Likert/SUS |
| I-5.1 | Recall ≥ 85 % | ≥ 85 % | ✅ 100 % | `honesto.json` |
| I-5.2 | Tiempo respuesta ≤ 3 s | ≤ 3 s | ✅ Medible por operación | `indicadores/12_tiempos_operacion.py` |
| I-5.3 | Tasa funcionamiento ≥ 90 % | ≥ 90 % | ✅ **100 %** (18/18) | `indicadores/15_tasa_pruebas.py` |
| I-5.4 | Disponibilidad ≥ 95 % | ≥ 95 % | ✅ **100 %** (30/30 pings, muestra corta) | `indicadores/13_disponibilidad.py` → `/api/v2/salud` |

---

## ✅ Indicadores ya cumplidos (o con la medición ya lista)

### I-1.1 — Volumen de datos
**Valor:** 21 corridas × 3 fuentes (metrics.log, events.log, sqlserver_logs.log). 353 ventanas train + 508 ventanas test = **861 ventanas**. Período cubierto: ver `inventario/cobertura_fechas.csv`.

**Para la tesis:** Tabla que diga:
> "Se recopilaron datos de 21 corridas (8 normales + 13 con fallos) provenientes de tres fuentes: métricas DMV, eventos Extended Events y Error Log de SQL Server, cubriendo 861 ventanas de 10 segundos."

---

### I-1.2 — Calidad de datos ≥ 95 %
**Valor real (medido):** `indicadores/11_indice_calidad.py` → `calidad_indice.json` sobre el
dataset completo (1050 filas × 74 columnas):
- Completitud: **99.73 %** (208 nulos / 77 700 celdas; casi todos en `log_error_count`/`log_fatal_count`)
- Consistencia: **100 %** (0 duplicados; marcas de tiempo ordenadas en todas las corridas)
- Validez: **99.43 %** (25 variables con rango; `cpu_sys` y `memory_percent` superan 100 en algunas filas)
- **Calidad = 99.72 % ✅**

> La corrección respecto a la estimación previa: el dataset tiene **74 columnas**, no 31, y
> **208 nulos**, no 100; aun así el índice supera la meta.

**Para la tesis:** Cita `calidad_indice.json` y la fórmula del indicador. El gráfico
`I-1.2_calidad_datos.png` es complementario.

---

### I-2.1 — F1-Score ≥ 85 %
**Valor oficial:** `honesto.json` → **F1 = 0.9639** (ENSEMBLE_LOF_ELL, LORO, q01). ✅

**Nota importante para la tesis:**
- Usa `honesto.json` como fuente oficial (Leave-One-Run-Out, normalizado por corrida).
- El valor 0.8136 de `metrics.json` es la **cota conservadora global** (test flat). Cítalo como referencia, no como valor del indicador.
- Ya tienes el gráfico `I-2.1_ranking_esquemas.png`.

---

### I-2.2 — Correlación |r| ≥ 0.6
**Valor:** `correlacion.json` → **51 pares** con |r| ≥ 0.6. Ya tienes `I-2.2_correlacion.png`.

**Para la tesis:** "Se identificaron 51 pares de variables con correlación de Pearson ≥ 0.6, lo que confirma la presencia de relaciones lineales significativas entre indicadores de rendimiento del OLTP."

---

### I-4.2 — Latencia ≤ 3 s
**Valor:** `latencia.json` → inferencia del modelo **0.22 ms/ventana**. Endpoints API: `GET /informes/resumen` 181 ms, `GET /alertas/{id}/informe` 224 ms → **< 0.5 s ✅**

---

### I-5.1 — Recall ≥ 85 %
**Valor:** ENSEMBLE_LOF_ELL detecta **155/155** ventanas de fallo (TPR = 100 %). En LORO: **13/13 corridas**. ✅
En 20 semillas: 0.9994 ± 0.0029. Gráfico: `evidencia_indicadores/graficos/I-5.1_recall_deteccion.png`
(generado por `indicadores/10_graficos_modelado.py`).

---

### I-5.2 — Tiempo de respuesta ≤ 3 s
Mismo valor que I-4.2. Endpoints clave < 0.5 s. **Medición formal por operación disponible:**
```bash
python indicadores/12_tiempos_operacion.py --n 30   # requiere backend en 8200 + STEELNORT_CLAVE
```
Mide login, dashboard, anomalías, alertas y resumen de reporte, y escribe
`indicadores/tiempos_operacion.json` (media y p95 por operación). ✅
Gráfico: `evidencia_indicadores/graficos/I-5.2_tiempos_operacion.png`.

---

### I-5.3 — Tasa de funcionamiento ≥ 90 %
**Resuelto (2026-10-15):** se creó la suite `backend/tests/` (18 pruebas) y el script
`indicadores/15_tasa_pruebas.py`, que corre pytest y calcula la tasa desde el JUnit XML:
```bash
python indicadores/15_tasa_pruebas.py
```
Resultado: **18/18 = 100 % ✅** (`tasa_pruebas.json`; XML en `reporte_pytest.xml`).
Gráfico: `evidencia_indicadores/graficos/I-5.3_tasa_pruebas.png`.

Las pruebas cubren funciones puras y el artefacto real, **sin base de datos**:
- `test_privacidad.py` (7): enmascarado de SQL (Ley N.° 29733).
- `test_detector.py` (4): carga del bundle de producción, umbrales ordenados, ventana de
  desplazamiento y marcado de una ventana extrema.
- `test_diagnostico.py` (7): `_severidad` (M/A/C), `_variables_desviadas` y `_regla_probable`.

---

## ⚠️ Indicadores con acción pendiente

### I-0 — Reducción del tiempo de detección
**Datos disponibles:** `diagnostico_final.json` tiene `ttfa_seg` por cada fallo (24/25 detectados,
TTFA entre 0 y 35 s). Ejecutado con `indicadores/14_auditar_pendientes.py`:

```bash
python indicadores/14_auditar_pendientes.py --ttd-pre 600
```

**Resultado (con TTD previo SUPUESTO de 600 s):** reducción **98.5 %**, **Wilcoxon p = 1.7e-05**
→ significativo (p < 0.05). Mediana del TTFA post = **4.0 s**, media 8.9 s.

> ⚠️ **Lo que falta de verdad:** el array `ttd_post` de una versión anterior de esta guía **no
> coincidía** con los valores reales de `diagnostico_final.json` (usaba 35/22 donde hay 32/28/19…).
> El script ahora los lee del artefacto. Pero el **TTD previo (O1) sigue siendo un supuesto**:
> I-0 es **[Propuesto]** y necesita que el gerente defina el tiempo de detección manual real.
> Sin ese dato, el contraste es significativo *frente al supuesto*, no una medición acreditada.

**Para la tesis (cuando tengas el O1):** "El sistema redujo el TTFA de ~X minutos (revisión manual)
a una mediana de 4 s (reducción del NN %, p < 0.001, Wilcoxon)."

> Referencia real ya medida en producción: MTTD p50 = 100.5 s (min 18.8 s, n = 19).

---

### I-3.1 — Precisión de clasificación por tipo ≥ 90 %
**Criterio adoptado: Top-2.** El sistema presenta al usuario las **dos** categorías más probables
(capa de apoyo al diagnóstico, RF5), por lo que la meta se evalúa sobre el Top-2.

- Clasificador supervisado (`clasificador_tipo.json`, RandomForest LORO por ventana, 155 ventanas):
  **Top-2 96.13 % ✅** · Top-1 66.45 % · Top-3 98.06 %.
- Por evento (lo que ve el usuario): **Top-2 91.7 %** · Top-1 75 %.
- Regla de auditoría R1-R7 (variable de mayor \|z\|): Top-1 20.8 % (queda como traza, no decide).

> "Se adoptó el criterio **Top-2** porque el sistema presenta al usuario las dos categorías más
> probables. El 96.13 % de las ventanas de fallo tienen el tipo correcto entre las dos primeras
> predicciones (LORO, 155 ventanas), cumpliendo la meta ≥ 90 % bajo ese criterio."

⚠️ **Honestidad para la defensa:** con la meta literal (**Top-1**) el indicador **NO cumple**
(mejor 66.45 % por ventana, 75 % por evento). El Top-1 está topado por la confusión
`fault2 ↔ fault5` (ambos son carga de E/S) y `fault3 → fault2`; no es un problema de ajuste del
modelo. Si el jurado exige Top-1, no se alcanza.

Tipos evaluados: `fault1`, `fault2`, `fault3`, `fault5`, `lockwait`. Gráficos: `I-3.1_topk_tipo.png`,
`I-3.1_matriz_confusion.png`.

---

### I-3.2 — Coincidencia de severidad ≥ 90 %
**Situación real: NO MEDIBLE.** Los escenarios del repo (`anomalias_timeline.csv` y `origen.json`)
solo traen `tipo, inicio, fin` — **no definen severidad esperada**. El propio
`03_evaluar_oe3.py` lo declara: *"I-3.2 severidad: sin ground truth, solo distribución"*.
Lo único reportable es la severidad **emitida**: **M 4 / A 20** (24 fallos).

⚠️ La versión anterior de esta guía proponía un mapa `{lockwait:A, fault1:A, fault2:A, fault3:M,
fault5:A}` **inventado**. Calculado con ese mapa (hipotético, `14_auditar_pendientes.py --sev`) da
**62.50 % < 90 %** → tampoco cumple. Es un supuesto sin respaldo, no acredita el indicador.

**Qué falta de verdad:** que cada escenario inyectado defina su severidad esperada
(p. ej. una columna `severidad` en `anomalias_timeline.csv`). Gráfico: `I-3.2_severidad_deteccion.png`.

---

### I-3.3 — Efectividad del diagnóstico ≥ 85 %
**Situación: ✅ CUMPLE — 91.67 % (22/24).** `diagnostico_final.json` trae
`efectividad_diagnostico = 0.9167`. Un diagnóstico se cuenta correcto si `coincide_huella` no está
vacío (alguna variable detectada está en la huella esperada `FOOTPRINT`).

**Qué cambió (fix real).** La medición anterior (54.17 %) tomaba **solo la primera ventana alertada**
del evento. El diagnóstico que ve el usuario es el del **evento completo**: el sistema ahora
**acumula** las variables que se desvían mientras la alerta sigue abierta
(`v2/services/anomalia_v2.py::_ampliar_alerta`) y la medición (`03_evaluar_oe3.py`) evalúa esa unión.

| Momento del diagnóstico | Coincidencia |
|---|---|
| **Evento completo (oficial)** | **91.67 % (22/24) ✅** |
| Ventana más fuerte (pico) | 79.17 % (19/24) |
| Solo la primera ventana (medición vieja) | 54.17 % (13/24) |

Reproducible con:
```bash
python indicadores/03_evaluar_oe3.py
python indicadores/14_auditar_pendientes.py
```

⚠️ **Honestidad para la defensa:** el pico aislado (79 %) no alcanza 85 %. Cumple porque el
diagnóstico describe el **evento**, no una sola ventana (mismo criterio "por evento" que I-3.1).

**Alinear la huella `FOOTPRINT` al modelo sigue siendo un no-op** (verificado): las coincidencias ya
son variables del modelo. Gráfico: `I-3.3_efectividad_diagnostico.png`.

---

### I-4.1 — Cumplimiento RF+RNF 100 %
**Solución:** Llena la matriz de verificación del `Indicadores.md`. Es manual pero rápida:

| RF/RNF | ¿Implementado? | Evidencia |
|--------|---------------|-----------|
| RF1 Auth | ✅ | JWT en backend, roles en BD |
| RF2 Recopilación | ✅ | pipeline/ + inventario_corridas.csv |
| RF3 Procesamiento | ✅ | dataset_steelnort.parquet |
| RF4 Detección | ✅ | ENSEMBLE_LOF_ELL en produccion/ |
| RF5 Alertas | ✅ | diagnostico.json + alertas API |
| RF6 Dashboard | ✅ | Frontend React con gráficos |
| RF7 Reportes | ✅ | /informes endpoint |
| RNF1 Seguridad | ✅ | JWT + HTTPS en .env |
| RNF2 Rendimiento | ✅ | < 0.5 s (latencia.json) |
| RNF3 Disponibilidad | ⚠️ | Ver I-5.4 (falta medición) |
| RNF4 Escalabilidad | ✅ | Módulos separados |
| RNF5 Usabilidad | ⚠️ | Depende de encuesta I-4.3 |
| RNF6 Mantenibilidad | ✅ | pipeline/, modelado/, app/ separados |
| RNF7 Integración | ✅ | REST API + pruebas |

> **Estado real del 100 % (actualizado 2026-10-15):** el servidor Web Push ya **arranca y está
> configurado**. Se creó `frontend/server/package.json`, se instalaron sus dependencias
> (`express`, `socket.io`, `dotenv`, `web-push`, `http-proxy-middleware`, `helmet`, `morgan`,
> `express-rate-limit`) y se creó `frontend/server/.env` (claves VAPID + `INTERNAL_TOKEN` alineado
> con `V2_INTERNAL_TOKEN` del backend). Verificado: `pushEstado()` → `{habilitado:true,…}` y
> `GET /internal/push/estado` → 200.
> Pendiente para el 100 %: **RNF3** (depende de I-5.4, medición de disponibilidad) y **RNF5**
> (depende de I-4.3, encuesta). Nota: quedó un `.env` duplicado mal ubicado en `frontend/src/.env`
> (puede borrarse).

---

### I-4.3 — Satisfacción de usuarios ≥ 80 %
**Es la única acción pendiente que REQUIERE acción externa.**

**Solución práctica:**
1. Crea un formulario de Google Forms con 5-8 preguntas en escala Likert 1-5 sobre el dashboard, las alertas y los reportes.
2. Aplícalo al gerente + 2-3 usuarios autorizados del OLTP.
3. Calcula: `respuestas con puntaje ≥ 4 / total × 100`

**Alternativa más rápida:** Cuestionario SUS de 10 preguntas estándar (≥ 68 puntos = aceptable).

---

### I-5.4 — Disponibilidad ≥ 95 %
**Endpoints de salud que existen:**
- Backend FastAPI: `GET http://localhost:8200/api/v2/salud` (comprueba BD + esquema).
- Server Express: `GET http://localhost:3000/health` (y `/healthz`).

⚠️ La versión anterior de esta guía decía `http://localhost:8000/health`: **el puerto estaba mal**
(el backend es 8200; el `/health` del Express es 3000).

**Solución (script listo):**
```bash
python indicadores/13_disponibilidad.py --base http://localhost:8200/api/v2 --pings 30 --intervalo 10
python indicadores/13_disponibilidad.py --duracion 3600   # 1 hora de observación
```
Registra `ok/total` y escribe `indicadores/disponibilidad.json`. Con el backend apagado da 0 %, así
que la medición hay que hacerla **con el sistema en operación** durante el periodo de prueba.
Gráfico: `evidencia_indicadores/graficos/I-5.4_disponibilidad.png`.

---

## 🧩 Scripts de medición (nuevos, aditivos)

| Indicador | Script | Salida |
|-----------|--------|--------|
| I-1.2 | `indicadores/11_indice_calidad.py` | `indicadores/calidad_indice.json` |
| I-5.2 | `indicadores/12_tiempos_operacion.py` | `indicadores/tiempos_operacion.json/.csv` |
| I-5.4 | `indicadores/13_disponibilidad.py` | `indicadores/disponibilidad.json` |
| I-0, I-3.2, I-3.3 | `indicadores/14_auditar_pendientes.py` | `indicadores/auditoria_pendientes.json` |
| I-5.3 | `indicadores/15_tasa_pruebas.py` | `indicadores/tasa_pruebas.json` + `reporte_pytest.xml` |
| I-1.2 … I-5.4 | `indicadores/10_graficos_modelado.py` | `indicadores/graficos/*.png` (incluye **I-5.1…I-5.4**) |

---

## 📋 Prioridad de acciones (revisada)

| Prioridad | Acción | Estado |
|-----------|--------|--------|
| 🔴 Alta | Encuesta I-4.3 (Likert/SUS) — **única acción externa** | Pendiente (no lo puedo hacer yo) |
| 🔴 Alta | I-3.2: etiquetar la severidad esperada por escenario | Bloqueado por datos |
| 🔴 Alta | I-3.3 / I-3.1: mejorar la señal (el techo es del detector) | Abierto |
| 🟡 Media | I-0: obtener el TTD previo real (O1) del gerente | Bloqueado por el gerente |
| 🟡 Media | I-5.3: crear la suite `pytest` | ✅ Hecho (18/18 = 100 %) |
| 🟢 Baja | I-4.1: `package.json` del server push + `npm install` + `.env` | ✅ Hecho (server arranca) |
| 🟢 Baja | I-5.4: registrar la disponibilidad con el sistema en operación | Script listo |
| ✅ Hecho | I-1.2 (99.72 %), I-5.2 (medición por operación), I-5.3 (100 %), I-4.1 (Web Push configurado) | Cumple |
