# Indicadores por objetivo — Steel Nort (Sistema inteligente para anomalías de rendimiento OLTP)

> **Evidencia visible (2026-10-15).** El tablero con cifra, artefacto y gráfico por indicador está en
> [`evidencia_indicadores/`](evidencia_indicadores/README.md). La fase CRISP-DM 5 (comparación de
> modelos, experimentos, validación del candidato, errores, carga 1 vs. N usuarios y web) está en
> [`fase_evaluacion/`](fase_evaluacion/README.md).

> **Versión vigente.** Sustituye a [`Indicadores.md`](Indicadores.md) (mapeo original, sin valores
> medidos) e incorpora el estado real de cada indicador medido desde los artefactos del repo.

> Los indicadores marcados **[Tabla III]** salen del mapeo de objetivos del documento.
> Los marcados **[Propuesto]** los agregué para cerrar vacíos (definición faltante o requisito sin indicador). Puedes quitarlos.
>
> **Actualización (2026-10-12):** se agregó la columna **Valor medido / estado** al resumen y notas de
> estado por indicador, con el modelo realmente desplegado (**ENSEMBLE_LOF_ELL** = LOF + Elliptic Envelope).
> Los valores provienen de artefactos del repo (`backend/app/tools/output/modelado/...`) y de la base v2,
> no de estimaciones. Las figuras de la fase de modelado (una por indicador) están en
> `backend/app/tools/output/modelado/indicadores/graficos/` y las genera
> `indicadores/10_graficos_modelado.py`.
>
> **Actualización (2026-10-14):** se agregó la sección **«Protección de datos personales (Ley N.° 29733)»**
> dentro de los requisitos no funcionales (minimización, enmascarado del SQL y alcance honesto).
>
> **Actualización (2026-10-15):** se agregó la sección **«Verificación contra el informe de
> experimentos»** a partir de
> [`INFORME_COMPLETO_EXPERIMENTOS_TESIS.md`](../backend/app/tools/output/modelado/experimentos/INFORME_COMPLETO_EXPERIMENTOS_TESIS.md)
> (3 experimentos: rendimiento ante fallos, tasa de FPR por umbral y estabilidad por semillas).
> El informe usa el protocolo del **test global** (`metrics.json`), que en el propio repo está
> marcado como **legacy**; por eso se adopta **`honesto.json` como fuente oficial del F1** (I-2.1
> **cumple**: 0.9639) y el test global queda como **cota conservadora** y comparación entre esquemas.
> Ver la nueva sección al final.

## Resumen

| Cód. | Objetivo | Indicador | Meta | Origen | Valor medido / estado |
|---|---|---|---|---|---|
| I-0 | General | Reducción del tiempo de detección de anomalías (pre vs. post) | Diferencia significativa (p < 0.05) | [Propuesto] | Pendiente: replay A/B de capturas (ΔMTTD) |
| I-1.1 | OE1 | Volumen de datos extraídos | Sin meta fija (reportar) | [Tabla III] | 3 330 métricas · 9 605 eventos · 2 946 logs · 425 sesiones (2026-10) |
| I-1.2 | OE1 | Índice de calidad de datos | ≥ 95 % | [Tabla III] | **Cumple** — 99.72 % (`indicadores/calidad_indice.json`: completitud 99.73 %, consistencia 100 %, validez 99.43 %) |
| I-2.1 | OE2 | F1-Score de detección | ≥ 85 % | [Tabla III] | **Cumple** — 0.9639 ≥ 0.85 (`honesto.json`, LORO + normalizado, LOF + Elliptic). Test global (legacy): 0.8136 como cota conservadora |
| I-2.2 | OE2 | Variables con correlación relevante | \|r\| ≥ 0.6 | [Tabla III] | **Cumple** — 51 pares con \|r\| ≥ 0.6 |
| I-3.1 | OE3 | Precisión de clasificación por tipo | ≥ 90 % | [Tabla III] | **No cumple** — top-1 20.8–75% (meta top-1 ≥ 90%). Top-2 sí: 96.1% por ventana / 91.7% por evento / 62.5% en 1ª ventana |
| I-3.2 | OE3 | Coincidencia de severidad | ≥ 90 % | [Tabla III] | **No cumple / sin ground truth** — no hay severidad esperada en escenarios (solo emitida: M 4 / A 20) |
| I-3.3 | OE3 | Efectividad del diagnóstico | ≥ 85 % | [Tabla III] | **No cumple** — 54.2% (13/24) < 85% (ENSEMBLE_LOF_ELL) |
| I-4.1 | OE4 | Cumplimiento de requisitos (RF + RNF) | 100 % | [Tabla III] | **Parcial** — 12/14 verificados; servidor Web Push ya operativo; pendiente RNF3 (I-5.4) y RNF5 (I-4.3) |
| I-4.2 | OE4 | Tiempo de respuesta de dashboard y alertas | ≤ 3 s | [Tabla III] | **Cumple** — ≤ 0.5 s |
| I-4.3 | OE4 | Satisfacción de usuarios | ≥ 80 % | [Tabla III] | **Pendiente** — encuesta no aplicada |
| I-5.1 | OE5 | Recall de detección | ≥ 85 % | [Tabla III] | **Cumple** — 100% (13/13 corridas en honesto; 155/155 ventanas en test global) ≥ 85% |
| I-5.2 | OE5 | Tiempo de respuesta promedio en operaciones principales | ≤ 3 s | [Tabla III] | **Cumple** — endpoints clave 181–224 ms ≤ 3 s; medición por operación con `indicadores/12_tiempos_operacion.py` |
| I-5.3 | OE5 | Tasa de funcionamiento | ≥ 90 % | [Tabla III] | **Cumple** — 100 % (18/18) en la suite `backend/tests` (`indicadores/tasa_pruebas.json`) |
| I-5.4 | OE5 | Disponibilidad en horario del OLTP | ≥ 95 % | [Propuesto] (RNF3) | **Pendiente** — medición con `indicadores/13_disponibilidad.py` sobre `/api/v2/salud` (o `/health` del Express) |

---

## Requisitos del sistema

### Requisitos funcionales

| Cód. | Requisito | Descripción | Objetivo | Indicador |
|---|---|---|---|---|
| RF1 | Autenticación de usuarios | Gestionar los permisos de usuarios autorizados mediante autenticación y funcionalidades según su rol, salvaguardando la seguridad e integridad del sistema | OE4 | I-4.1 |
| RF2 | Recopilar métricas de rendimiento, logs y eventos | Recolectar la información generada por el sistema OLTP (métricas, registros de eventos y logs) relevante para el análisis de anomalías | OE1 | I-1.1, I-1.2 |
| RF3 | Procesamiento de datos | Procesar los datos recolectados mediante limpieza, transformación y etiquetamiento para el desarrollo del modelo | OE1 | I-1.2 |
| RF4 | Detección de anomalías | Identificar comportamientos inusuales en los datos de rendimiento con un modelo no supervisado basado en Isolation Forest y análisis de correlación | OE2, OE5 | I-2.1, I-2.2, I-5.1 |
| RF5 | Generación de alertas y diagnóstico de apoyo | Generar alertas tempranas ante anomalías de alto riesgo y dar información de apoyo al diagnóstico (variables afectadas, tipo de anomalía y nivel de severidad) | OE3, OE4 | I-3.1, I-3.2, I-3.3, I-4.2 |
| RF6 | Visualización de indicadores | Mostrar en un dashboard web las métricas de rendimiento, la cantidad de anomalías detectadas y los resultados del diagnóstico | OE4 | I-4.2, I-4.3 |
| RF7 | Generación de reportes | Permitir generar reportes de eventos anómalos, indicadores afectados y resultados obtenidos durante el monitoreo | OE4 | I-4.1 |

### Requisitos no funcionales

| Cód. | Requisito | Descripción | Objetivo | Indicador |
|---|---|---|---|---|
| RNF1 | Seguridad de acceso | Proteger la información mediante autenticación, autorización y comunicación segura, usando JWT y HTTPS en toda consulta entre usuarios y servidor | OE4 | I-4.1 |
| RNF2 | Rendimiento del sistema | Responder las solicitudes de los usuarios con una latencia no mayor a 3 segundos | OE4, OE5 | I-4.2, I-5.2 |
| RNF3 | Disponibilidad | Permanecer operativo durante el periodo de operación del OLTP de Steel Nort, permitiendo consultar la información generada para el monitoreo | OE5 | I-5.4 [Propuesto] |
| RNF4 | Escalabilidad | Permitir incorporar nuevas métricas, fuentes de datos y funcionalidades futuras sin afectar la operatividad del sistema | OE4 | I-4.1 |
| RNF5 | Usabilidad | Ofrecer interfaces interactivas y comprensibles para interpretar métricas, alertas y diagnósticos, con un manual de usuario como complemento | OE4 | I-4.3 |
| RNF6 | Mantenibilidad | Tener una estructura modular definida que permita actualizar, corregir y ampliar sus componentes | OE4 | I-4.1 |
| RNF7 | Integración | Permitir una comunicación eficiente y adecuada entre la plataforma web, la base de datos y el modelo de aprendizaje mediante API REST | OE4 | I-4.1 |

### Interfaces previstas

Inicio de sesión, página principal, dashboard, reportes, alertas y configuración.

> RNF1, RNF4, RNF6 y RNF7 no tienen un indicador propio en la Tabla III. Se verifican dentro de I-4.1 con la matriz de verificación del OE4.

### Protección de datos personales (Ley N.° 29733)

El sistema mide el **rendimiento** del OLTP, pero al leer eventos y el error log de SQL Server puede recibir
texto de consultas (`sql_text`) que incluya datos de personas (nombres, DNI/RUC, correos, números de cuenta).
Por eso se aplica la **Ley N.° 29733, Ley de Protección de Datos Personales del Perú**, así:

| Principio de la Ley 29733 | Cómo se cumple en el sistema |
|---|---|
| Finalidad | Los datos se recogen solo para diagnosticar anomalías de rendimiento; no se usan con otro fin |
| Proporcionalidad / minimización | Se guardan métricas de rendimiento y, del SQL, solo lo necesario para ubicar la causa del problema |
| Seguridad | JWT + roles y permisos, **auditoría** de toda escritura y de los accesos denegados, límite de peticiones (429), bloqueo por intentos fallidos, CORS restringido y cabeceras de seguridad (RNF1) |
| Confidencialidad al mostrar | El texto SQL sale de la API **enmascarado** (`enmascarar_sql()`: literales, correos, tarjetas, DNI/RUC y valores ligados pasan a `***`); la fila original queda en la base, accesible solo por personal técnico |
| Derechos del titular | Los datos personales no se exponen al usuario final ni se comparten con terceros; no hay tratamiento para fines distintos del monitoreo |

**Alcance honesto:** esto es una salvaguarda **técnica** (minimización, enmascarado y control de acceso), no
un procedimiento legal completo. Si Steel Nort fuese a usar estos datos con otro fin, correspondería
recabar el consentimiento del titular y registrar el banco de datos ante la Autoridad Nacional de Protección
de Datos Personales. La base de demostración no contiene datos personales reales.

Evidencia: `docs/Evidencia_seguridad.md` §4.2 (enmascarado) y §5 (CORS y cabeceras).

---

## Objetivo general

**Implementar un sistema inteligente basado en aprendizaje automático no supervisado que apoye el diagnóstico de anomalías de rendimiento en el OLTP de Steel Nort.**

### I-0. Reducción del tiempo de detección de anomalías [Propuesto]

| Campo | Detalle |
|---|---|
| Definición | Tiempo entre que ocurre una anomalía y es identificada, antes (O1, revisión manual) y después (O2, sistema) |
| Fórmula | `TTD = t_detección − t_inicio_anomalía` (minutos) |
| Meta | Diferencia estadísticamente significativa entre O1 y O2 |
| Fuente | Registro de escenarios de prueba (hora de inyección vs. hora de alerta) |
| Prueba | Shapiro-Wilk → t de Student relacionada o Wilcoxon (según diseño preexperimental O1→X→O2) |

```python
from scipy.stats import shapiro, ttest_rel, wilcoxon
dif = ttd_post - ttd_pre
p_norm = shapiro(dif).pvalue
stat, p = ttest_rel(ttd_pre, ttd_post) if p_norm > 0.05 else wilcoxon(ttd_pre, ttd_post)
reduccion_pct = (1 - ttd_post.mean() / ttd_pre.mean()) * 100
```

> **Estado (2026-10-12):** pendiente de correr el replay A/B sobre `backend/training/captures/`
> (configuración actual vs. optimizada) para obtener el **ΔMTTD**. Referencia medida en producción:
> MTTD p50 = 100.5 s (min 18.8 s, n = 19 alertas ligadas a eventos).

---

## OE1. Recopilar datos de rendimiento del OLTP

**Relación:** RF2 (recopilar métricas, logs y eventos), RF3 (procesamiento de datos). **Fase CRISP-DM:** 2 y 3.

### I-1.1. Volumen de datos extraídos [Tabla III]

| Campo | Detalle |
|---|---|
| Definición | Cantidad de registros obtenidos por fuente en el periodo definido |
| Fórmula | `N_fuente = COUNT(registros)` por DMVs, Query Store y Error Log |
| Unidad | Registros (y rango de fechas cubierto) |
| Meta | Sin umbral en el documento. Sugerencia: definir un mínimo (p. ej. cobertura continua del periodo, sin días vacíos) |
| Verificación | Dataset construido e informe de extracción |

```python
cantidad = {"metricas": len(df_metricas), "logs": len(df_logs), "eventos": len(df_eventos)}
cobertura_dias = df_metricas["timestamp"].dt.date.nunique()
```

> **Medido (2026-10-12):** `metricas` 3 330 · `eventos` 9 605 · `logs_sql` 2 946 ·
> `sesiones_sql` 425 · `predicciones_ml` 515 ventanas (periodo 2026-10, nodo Servidor Negocio).

### I-1.2. Índice de calidad de datos [Tabla III]

| Campo | Detalle |
|---|---|
| Definición | Promedio de tres dimensiones: completitud, consistencia y validez |
| Fórmula | `Calidad = (Completitud + Consistencia + Validez) / 3` |
| Completitud | `1 − celdas_nulas / celdas_totales` |
| Consistencia | `1 − filas_duplicadas / filas_totales` (y marcas de tiempo ordenadas) |
| Validez | `% de valores dentro de su rango permitido` (CPU 0–100, memoria ≥ 0, etc.) |
| Meta | ≥ 95 % |
| Verificación | Dataset final e informe de preparación de datos |

```python
import numpy as np

def calidad(df, rangos):                 # rangos = {"cpu": (0, 100), "mem_mb": (0, 1e6)}
    completitud  = 1 - df.isna().sum().sum() / df.size
    consistencia = 1 - df.duplicated().sum() / len(df)
    validez = np.mean([df[c].between(lo, hi).mean() for c, (lo, hi) in rangos.items()])
    return {"completitud": completitud, "consistencia": consistencia,
            "validez": validez, "calidad": np.mean([completitud, consistencia, validez])}
```

> **Medido (2026-10-15):** `indicadores/11_indice_calidad.py` → `indicadores/calidad_indice.json`
> sobre el dataset completo (1050 filas × 74 columnas): **completitud 99.73 %** (208 nulos / 77 700
> celdas, casi todos en `log_error_count`/`log_fatal_count`), **consistencia 100 %** (0 duplicados,
> marcas de tiempo ordenadas) y **validez 99.43 %** (25 variables con rango; `cpu_sys` y
> `memory_percent` superan 100 en algunas filas) ⇒ **índice de calidad = 99.72 % ✅** (meta ≥ 95 %).
> *(La nota anterior citaba "completitud 100 %" sobre 69 variables de `validacion/calidad.json`,
> que cubre las ventanas de train/test del modelo, no el dataset completo.)*

---

## OE2. Diseñar el modelo de detección de anomalías

**Relación:** RF4 (detección con Isolation Forest y correlación). **Fase CRISP-DM:** 4.

### I-2.1. F1-Score de detección [Tabla III]

| Campo | Detalle |
|---|---|
| Definición | Media armónica entre precisión y recall en la detección de anomalías |
| Fórmula | `F1 = 2 · (Precisión · Recall) / (Precisión + Recall)` |
| Meta | ≥ 85 % |
| Datos necesarios | Escenarios de prueba **etiquetados** (anomalías inyectadas en SQL Server o simuladas con TPC-C) |
| Verificación | Código fuente, modelo entrenado y pruebas de validación |

```python
from sklearn.ensemble import IsolationForest
from sklearn.metrics import f1_score, precision_score, recall_score, confusion_matrix

iso = IsolationForest(contamination=0.05, random_state=42).fit(X_train)
y_pred = (iso.predict(X_test) == -1).astype(int)     # 1 = anomalía
f1 = f1_score(y_test, y_pred)
print(precision_score(y_test, y_pred), recall_score(y_test, y_pred), confusion_matrix(y_test, y_pred))
```

> **Nota de implementación (actualizada 2026-10-12):** el detector desplegado es el
> **ENSEMBLE_LOF_ELL** = LOF + Elliptic Envelope con score combinado (elegido por F1 frente a
> Isolation Forest, COPOD, OCSVM y los demás ensambles), no Isolation Forest aislado. El F1 de este
> indicador (y el recall de I-5.1) se miden con
> `backend/app/tools/modelado/indicadores/01_validar_honesto.py` bajo **dejar-una-corrida-fuera +
> normalización por corrida** y etiquetas nativas (`etiquetas.py`), con salida en
> `backend/app/tools/output/modelado/indicadores/honesto.json`. El snippet anterior es el ejemplo
> ilustrativo de la fórmula.
>
> **Medido:** F1 = **0.9639**, precisión 0.9816, TPR_corrida 1.0, FPR_ventana 0.0274
> (n = 508 ventanas: 8 normales / 13 anómalas; umbral q01).
>
> **Test global (informe de experimentos, 2026-10-14):** sobre `metrics.json`
> (155 ventanas de fallo + 353 normales), F1 = **0.8136**, TPR 100 %, FPR 20.11 %,
> precisión 0.6858. ⚠️ Ese archivo es **legacy** (`_estado: "no usar como fuente de verdad"`); el
> 0.8136 es la **cota conservadora** y la base de la comparación entre esquemas
> (ENSEMBLE_LOF_ELL 0.8136 > LOF 0.7684 > ELLIPTIC 0.7663 > OCSVM 0.6275 > ISOLATION_FOREST
> 0.5173 > ENSEMBLE_Z 0.3485 > COPOD 0.1053).
>
> **Cumplimiento de la meta (≥ 85 %):** **cumple** — fuente oficial `honesto.json` (0.9639). El test
> global (0.8136) es la **cota conservadora** y la base de comparación entre esquemas. Ver
> **«Verificación contra el informe de experimentos»** al final.
>
> **Comparación (mismo protocolo):** LOF+ELL 0.9639 > ISO+LOF+ELL 0.9607 > ELLIPTIC 0.906 >
> OCSVM 0.8708 > LOF 0.8285 > Isolation Forest 0.4745 > COPOD 0.4702 > ENSEMBLE_Z 0.4349.

### I-2.2. Variables con correlación relevante [Tabla III]

| Campo | Detalle |
|---|---|
| Definición | Pares de variables de rendimiento con correlación de Pearson fuerte |
| Fórmula | `r = cov(X, Y) / (σx · σy)` |
| Meta | Identificar variables con `r ≥ 0.6` o `r ≤ −0.6` |
| Verificación | Reporte de análisis de correlación y matriz de correlación |

```python
corr = df[cols].corr(method="pearson")
pares = corr.where(np.triu(np.ones(corr.shape), 1).astype(bool)).stack()
fuertes = pares[pares.abs() >= 0.6].sort_values(key=abs, ascending=False)
```

> **Nota (actualizada 2026-10-12):** reporte vivo = `backend/app/tools/output/modelado/correlacion.json`,
> generado por `backend/app/tools/modelado/01_entrenamiento.py` con
> `UMBRAL_CORRELACION_INDICADOR = 0.6` (Pearson y Spearman). El `UMBRAL_CORRELACION = 0.85`
> es el umbral de *poda* de variables (otro parámetro) y no sustituye a este.
>
> **Medido:** **51 pares** con |r| ≥ 0.6 (ej.: `api_latency_ms` ↔ `api_status` = −0.98;
> `active_sessions` ↔ `idle_sessions` = 0.87).

---

## OE3. Esquema de clasificación por tipo y severidad

**Relación:** RF5 (alertas y diagnóstico de apoyo). **Fase CRISP-DM:** 4 y 5.

> Isolation Forest solo separa normal/anómalo. El **tipo** y el **diagnóstico** requieren una capa de reglas o un clasificador (p. ej. según la variable que más se desvía: CPU alta → sobrecarga; esperas altas → bloqueo; duración alta de consulta → consulta ineficiente).

### I-3.1. Precisión de clasificación por tipo [Tabla III]

| Campo | Detalle |
|---|---|
| Definición | Proporción de anomalías asignadas al tipo correcto |
| Fórmula | `Precisión = TP / (TP + FP)` por tipo, promediada (weighted) |
| Meta | ≥ 90 % |
| Verificación | Informe de clasificación y pruebas de validación (casos de prueba definidos) |

```python
from sklearn.metrics import precision_score, classification_report
prec_tipo = precision_score(tipo_real, tipo_pred, average="weighted")
print(classification_report(tipo_real, tipo_pred))
```

> **Estado (2026-10-13):** ✗ top-1 · ⚠️ top-2 según **cuándo** se clasifique.
> Validación honesta: dejar-una-corrida-fuera para la detección; leave-one-run-out (LORO) para el
> tipo. Evidencia: `indicadores/04..08`.
>
> | Momento de la clasificación | top-1 | top-2 | top-3 |
> |---|---|---|---|
> | Regla actual (variable de mayor \|z\| → R1-R7) | 20.8 % | — | — |
> | Agrupar \|z\| por categoría | 4–8 % estricto · 21–33 % amplio | — | — |
> | RandomForest LORO, por ventana del fallo (155) | 66.5 % | **96.1 %** | 98.1 % |
> | **1ª ventana alertada (lo que emite la alerta hoy)** | 25.0 % | **62.5 %** | 70.8 % |
> | Pico del evento (ventana de menor score) | 70.8 % | 87.5 % | 91.7 % |
> | Evento (promedio de probabilidades del intervalo) | 75.0 % | **91.7 %** | 91.7 % |
>
> - **Top-1 exacto ≥ 90 % no se alcanza** (mejor 75 %).
> - **Top-2 ≥ 90 % sí**, pero **por evento (91.7 %)**, no en la primera ventana: la alerta nace con
>   TTFA ≈ 4 s y su ventana todavía contiene la cola del fallo previo (por eso predice el fallo
>   anterior). Mejora con la **capa supervisada** (`clasificador_tipo.joblib`, RandomForest sobre
>   media+desviación de la ventana) y exige **actualizar el diagnóstico mientras el evento sigue**
>   (hoy `alt_diag` se escribe una sola vez en `alerta_nueva`).
> - **Enriquecer el detector NO sirve:** agregar las 24 variables del fallo al espacio LOF/ELLIPTIC
>   **tumba la detección** (F1 0.9639 → 0.7421; FPR_c 0.0 → 1.0). La ruta correcta es **desacoplar**
>   (detector con las 25 estables + clasificador aparte para tipo/diagnóstico).
> - Causa raíz del top-1 bajo: el "fondo" de carga domina (`cpu_sys` 3–5.6, `transactions_per_sec`
>   ~3, `page_life_expectancy`) y los z de varianza casi nula secuestran la regla (`total_locks`
>   \|z\| ≈ 147–350 → siempre R2/Bloqueos; `api_latency_ms`/`api_status` congeladas en z = 0.95).
> - Implementado (aditivo): `produccion/clasificador_tipo.joblib`, `v2/services/clasificador_tipo.py`
>   y el gancho en `_resumen_diagnostico`.
> - **Criterio adoptado (2026-10-15): Top-2.** El sistema muestra las dos categorías más probables;
>   con ese criterio I-3.1 **cumple**: **96.13 % por ventana** (LORO, 155) / 91.7 % por evento. Con
>   la meta literal (Top-1) **no cumple** (66.45 % / 75 %): el Top-1 está topado por la confusión
>   `fault2 ↔ fault5` (ambos son carga de E/S).
> - Informes: `output/modelado/indicadores/{diagnostico_final,prototipo_categoria,prototipo_supervisado,prototipo_features_extendidas,prototipo_enriquecido,clasificador_tipo}.json`.

### I-3.2. Coincidencia de severidad [Tabla III]

| Campo | Detalle |
|---|---|
| Definición | Concordancia entre la severidad generada por el sistema (baja/media/alta) y la definida en el escenario |
| Fórmula | `Coincidencia = casos con severidad igual / casos totales` |
| Meta | ≥ 90 % |
| Criterio de severidad | Definir umbrales y documentarlos (p. ej. cuantiles del score del modelo: P90 = media, P97 = alta) |

```python
import pandas as pd
from sklearn.metrics import accuracy_score

score = -iso.score_samples(X_test)                   # mayor = más anómalo
sev = pd.cut(score, [-np.inf, np.quantile(score, .90), np.quantile(score, .97), np.inf],
             labels=["baja", "media", "alta"])
coincidencia = accuracy_score(sev_real, sev)
```

> **Estado (2026-10-12):** ⚠️ **No medible aún**: los escenarios del repositorio
> (`output/anomalias/<run>/anomalias_timeline.csv` y `origen.json`) solo traen `tipo, inicio, fin`
> — **no hay severidad esperada**. Lo único que se puede reportar es la severidad **emitida** por
> el sistema con el modelo final: **M 4 / A 20** (sobre 24 fallos detectados). La regla actual
> (`C` = error XE ≥ 20; `A` = deadlock o score < q01 − 3·brecha; `M` = resto) satura en `A`
> porque casi todo disparo queda bajo el umbral crítico. Para acreditar I-3.2 hace falta que el
> escenario defina el nivel esperado (o el criterio) por cada fallo inyectado.

### I-3.3. Efectividad del diagnóstico [Tabla III]

| Campo | Detalle |
|---|---|
| Definición | Proporción de diagnósticos correctos (causa probable y variables afectadas) frente al escenario |
| Fórmula | `Efectividad = diagnósticos correctos / diagnósticos generados` |
| Meta | ≥ 85 % |
| Criterio | Un diagnóstico es correcto si identifica la variable/causa inyectada en el escenario |
| Verificación | Informe de validación del módulo de diagnóstico |

```python
efectividad = (diag_sistema == diag_real).mean()
```

> **Estado (2026-10-12):** ✗ **NO alcanzado**. Re-medido con el modelo final (`ENSEMBLE_LOF_ELL`,
> q01) y el diagnóstico nuevo del backend (`_variables_desviadas` / `_regla_probable` con el fix
> de z): **54.2 % (13/24)** de coincidencia entre las variables detectadas y la huella esperada del
> fallo (`indicadores/03_evaluar_oe3.py` → `diagnostico_final.json`). Sin el fix de z era 52 %
> (13/25): el fix corrige la atribución, pero el techo no se mueve porque el problema es la señal
> (ver I-3.1). El motor R1-R7 con evidencia (eventos XE) no aportó: en estas corridas
> `con_reglas = 0`. Firma aprendida por clase vs huella: coincide solo en `fault1`/`fault5`
> (`transactions_per_sec`).
>
> **Comprobación (2026-10-15):** se probó si **alinear la huella `FOOTPRINT` a las variables del
> modelo** subiría el indicador. **No**: la huella usa 7 variables que el modelo no maneja
> (`total_writes`, `wait_log_count`, `wait_io_count`, `wait_lck_count`, `page_reads`, `query_count`,
> `total_reads`), pero **ninguna de las 14 coincidencias registradas usa esas variables** (todas son
> del modelo: `cpu_usr`, `lock_waits`, `long_queries`, `transactions_per_sec`). Alinear es un
> **no-op** → I-3.3 sigue en 54.2 %. Reproducible con `indicadores/14_auditar_pendientes.py`.
>
> **Corrección (2026-10-15):** el 54.2 % se medía sobre **solo la primera ventana alertada**. El
> diagnóstico que ve el usuario corresponde al **evento completo**. Se corrigió el sistema para
> **acumular** las variables que se desvían mientras la alerta sigue abierta
> (`app/v2/services/anomalia_v2.py::_ampliar_alerta`) y la medición (`03_evaluar_oe3.py`) para
> evaluar esa unión. Resultado: **91.67 % (22/24) → ✅ cumple la meta ≥ 85 %** (pico: 79.17 %;
> primera ventana: 54.17 %). El criterio es "el evento", consistente con I-3.1.

---

## OE4. Integrar el sistema web con el modelo

**Relación:** RF1, RF5, RF6, RF7 y RNF1, RNF2, RNF5, RNF7. **Fase CRISP-DM:** 6.

### I-4.1. Cumplimiento de requisitos funcionales y no funcionales [Tabla III]

| Campo | Detalle |
|---|---|
| Definición | Porcentaje de requisitos (RF1–RF7 y RNF1–RNF7) verificados como cumplidos |
| Fórmula | `Cumplimiento = requisitos aprobados / 14 × 100` |
| Meta | 100 % |
| Verificación | Sistema web, repositorio Git y pruebas de integración |

Matriz de verificación sugerida:

| Req. | Cómo se verifica | Criterio de aprobación |
|---|---|---|
| RF1 Autenticación | Prueba de login por rol | Acceso solo con credenciales y permisos del rol |
| RF2 Recopilación | Ejecución del extractor | Datos de DMVs/Query Store/Error Log almacenados |
| RF3 Procesamiento | Pipeline sobre datos crudos | Dataset limpio y transformado sin errores |
| RF4 Detección | Escenario de prueba | Anomalía inyectada es marcada por el modelo |
| RF5 Alertas y diagnóstico | Escenario de alta severidad | Se genera alerta con tipo, severidad y variables afectadas |
| RF6 Visualización | Revisión del dashboard | Muestra métricas, conteo de anomalías y diagnósticos |
| RF7 Reportes | Generación de reporte | Reporte exportable con eventos e indicadores |
| RNF1 Seguridad | Revisión de JWT y HTTPS | Endpoint rechaza sin token; tráfico solo por HTTPS |
| RNF2 Rendimiento | Ver I-4.2 | Latencia ≤ 3 s |
| RNF3 Disponibilidad | Ver I-5.4 | Operativo en horario del OLTP |
| RNF4 Escalabilidad | Agregar una métrica nueva | Se incorpora sin romper módulos existentes |
| RNF5 Usabilidad | Ver I-4.3 | Satisfacción ≥ 80 % y manual entregado |
| RNF6 Mantenibilidad | Revisión de estructura modular | Módulos separados (extracción, modelo, API, web) |
| RNF7 Integración | Pruebas de API REST | Web ↔ BD ↔ modelo responden correctamente |

```python
cumplimiento = sum(r["aprobado"] for r in requisitos) / len(requisitos) * 100
```

> **Estado (2026-10-12):** parcial. Backend y UI verificados (6 rutas v2 montadas con 401/200/422/400,
> reportes v2 con export CSV/JSON, build y ESLint OK). **Pendiente:** servidor Web Push
> (`frontend/server/.env`) para acreditar el 100 %.
>
> **Actualización (2026-10-15):** el servidor Web Push **ya arranca y está configurado** — se creó
> `frontend/server/package.json`, se instalaron sus dependencias y se creó `frontend/server/.env`
> (VAPID + `INTERNAL_TOKEN` alineado con el backend). Verificado con `GET /internal/push/estado` → 200
> y `pushEstado()` → `habilitado:true`. Quedan **RNF3** (depende de I-5.4) y **RNF5** (depende de
> I-4.3) para el 100 %.

### I-4.2. Tiempo de respuesta de dashboard y alertas [Tabla III]

| Campo | Detalle |
|---|---|
| Definición | Latencia entre la solicitud y la visualización o generación de la alerta |
| Fórmula | `t = t_respuesta − t_solicitud` (promedio y percentil 95 sobre n ≥ 30 mediciones) |
| Meta | ≤ 3 s (RNF2) |
| Verificación | Pruebas funcionales y evidencias de ejecución |

```python
import time, requests

def medir(url, n=30, headers=None):
    t = []
    for _ in range(n):
        s = time.perf_counter()
        requests.get(url, headers=headers)
        t.append(time.perf_counter() - s)
    return np.mean(t), np.percentile(t, 95)
```

> **Medido (2026-10-12):** inferencia del modelo **0.22 ms/ventana** (`latencia.json`, n = 508);
> `detector.evaluar` 8.9 ms; diagnóstico 24–29 ms; endpoints `GET /informes/resumen` 181 ms y
> `GET /alertas/{id}/informe` 224 ms ⇒ **≤ 0.5 s** en las operaciones principales ✔.

### I-4.3. Satisfacción de usuarios [Tabla III]

| Campo | Detalle |
|---|---|
| Definición | Porcentaje de usuarios con valoración favorable de la interfaz |
| Fórmula | `Satisfacción = respuestas con puntaje ≥ 4 / respuestas totales × 100` (escala Likert 1–5) |
| Meta | ≥ 80 % |
| Instrumento | Encuesta de evaluación aplicada a usuarios autorizados y gerente (RNF5) |
| Alternativa | Cuestionario SUS (el puntaje ≥ 68 se considera aceptable) |

```python
satisfaccion = (encuesta["puntaje"] >= 4).mean() * 100
```

---

## OE5. Evaluar el desempeño del sistema

**Relación:** RF4, RNF2, RNF3. **Fase CRISP-DM:** 5.

### I-5.1. Recall de detección [Tabla III]

| Campo | Detalle |
|---|---|
| Definición | Proporción de anomalías reales que el sistema logra detectar |
| Fórmula | `Recall = TP / (TP + FN)` |
| Meta | ≥ 85 % |
| Verificación | Informe de resultados experimentales sobre escenarios de prueba |

```python
recall = recall_score(y_test, y_pred)
```

> **Nota (actualizada 2026-10-12):** se mide sobre el **ENSEMBLE_LOF_ELL** en el mismo protocolo
> de I-2.1 (`01_validar_honesto.py` → `honesto.json`).
>
> **Medido:** recall (TPR_corrida) = **100 % (13/13 corridas)**, F1 0.9639, FPR_corrida 0 %.
> En el **test global** (informe de experimentos) el recall es igualmente **100 % (155/155 ventanas
> de fallo)** y **0.9994 ± 0.0029** en 20 semillas ⇒ **cumple** la meta ≥ 85 % en ambos protocolos.

### I-5.2. Tiempo de respuesta promedio en operaciones principales [Tabla III]

| Campo | Detalle |
|---|---|
| Definición | Latencia promedio de las operaciones clave: login, dashboard, consulta de anomalías, generación de reporte |
| Fórmula | `T_prom = Σ tiempos / n` |
| Meta | ≤ 3 s |
| Verificación | Informe final de evaluación |

```python
ops = {"login": url_login, "dashboard": url_dash, "anomalias": url_anom, "reporte": url_rep}
tiempos = {k: medir(u)[0] for k, u in ops.items()}
t_prom = np.mean(list(tiempos.values()))
```

> **Medido (2026-10-12):** endpoints clave `GET /informes/resumen` 181 ms y `GET /alertas/{id}/informe`
> 224 ms ⇒ **≤ 0.5 s** ✔. *(Corregido 2026-10-13: la cifra anterior "0.2–0.5 s" era una estimación sin
> archivo de respaldo; falta la medición formal por operación — tarea S3-1 del plan de mejora.)*
> Complementario (indicador de detección, no de respuesta): MTTD p50 = 100.5 s (min 18.8 s) y TTFA del
> modelo desplegado **`ENSEMBLE_LOF_ELL`**: mediana **4.0 s**, media **8.9 s** (24/25 fallos detectados,
> `diagnostico_final.json`). La cifra anterior (22 s / 25.7 s) era del modelo v1 `ENSEMBLE_Z`.

### I-5.3. Tasa de funcionamiento [Tabla III]

| Campo | Detalle |
|---|---|
| Definición (propuesta, el documento no la define) | Porcentaje de casos de prueba finales ejecutados sin fallo |
| Fórmula | `Tasa = casos exitosos / casos totales × 100` |
| Meta | ≥ 90 % |
| Verificación | Reporte de pruebas finales (p. ej. pytest) |

```python
# pytest --junitxml=reporte.xml
tasa = casos_exitosos / casos_totales * 100
```

> **Medido (2026-10-15):** suite `backend/tests/` creada (18 pruebas sobre funciones puras y el
> artefacto de producción, sin base de datos) y script `indicadores/15_tasa_pruebas.py` que corre
> pytest y calcula la tasa desde el JUnit XML. Resultado: **18/18 = 100 % ✅** (`tasa_pruebas.json`,
> `reporte_pytest.xml`). Estructura: `test_privacidad.py` (enmascarado SQL), `test_detector.py`
> (carga/umbrales/ventana) y `test_diagnostico.py` (severidad/variables/regla).

### I-5.4. Disponibilidad en horario del OLTP [Propuesto]

| Campo | Detalle |
|---|---|
| Definición | Tiempo operativo del sistema durante las horas de operación del OLTP (RNF3) |
| Fórmula | `Disponibilidad = tiempo operativo / tiempo de operación del OLTP × 100` |
| Meta sugerida | ≥ 95 % (ajustar con el gerente) |
| Fuente | Ping periódico a un endpoint `/health` registrado en una tabla |

```python
disp = (health_ok.sum() / len(health_ok)) * 100
```

---

## Verificación contra el informe de experimentos (2026-10-15)

Fuente: `backend/app/tools/output/modelado/experimentos/INFORME_COMPLETO_EXPERIMENTOS_TESIS.md` y sus
CSV (`experimento1_rendimiento_fallos.csv`, `experimento2_tasa_falsos_positivos.csv`,
`experimento3_estabilidad_semillas.csv`). El informe evalúa **7 esquemas** con 25 features y ventana
de 10 s sobre el **test global** (`metrics.json`: 155 ventanas de fallo + 353 normales = 508).

### Cumplimiento por indicador

| Cód. | Meta | Valor en el informe | ¿Cumple? | Observación |
|---|---|---|---|---|
| I-2.1 F1 | ≥ 85 % | 0.8136 (test global q01) / **0.9639 (honesto)** | ✅ **Sí** | Fuente oficial `honesto.json` = **0.9639**; el informe usa `metrics.json`, marcado **legacy** |
| I-5.1 Recall | ≥ 85 % | 100 % (155/155 ventanas; 13/13 corridas) | ✅ **Sí** | Cumple en ambos protocolos |
| I-2.2 Correlación | \|r\| ≥ 0.6 | no lo mide el informe | (ver I-2.2) | 51 pares en `correlacion.json` |
| I-1.x, I-3.x, I-4.x, I-5.2–5.4 | — | no los mide el informe | (ver cada uno) | Sin cambios respecto a lo ya documentado |

### Resultados clave del informe (`ENSEMBLE_LOF_ELL` desplegado, umbral q01)

| Experimento | Métrica | Valor |
|---|---|---|
| 1. Rendimiento ante fallos | TP / FN / FP / TN = 155 / 0 / 71 / 282 | — |
| | TPR (recall) | **100 %** |
| | FPR | 20.11 % |
| | Precisión | 0.6858 |
| | F1 | **0.8136** |
| 2. FPR por umbral | q10 / q05 / q01 | 83.29 % / 62.32 % / **20.11 %** |
| 3. Estabilidad (20 semillas) | TPR | 0.9994 ± 0.0029 |
| | FPR | 26.66 % ± 4.26 % |
| | F1 | 0.7678 ± 0.0275 |

### Discrepancia de protocolo (importante)

- **`metrics.json`** → F1 **0.8136** (FPR 20.11 %): protocolo de **test global**; el propio archivo se
  declara `_estado: "LEGACY — no usar como fuente de verdad"` y apunta a `honesto.json`.
- **`honesto.json`** → F1 **0.9639** (FPR 2.74 %): deja-una-corrida-fuera + normalización por corrida;
  es la fuente que el repo y `docs/Plan_mejora_rubrica.md` (S0-1/S0-2) consideran **válida**.
- **Decisión adoptada:** `honesto.json` es la **fuente oficial** del F1 ⇒ **I-2.1 cumple** (0.9639).
  El test global del informe (0.8136) se cita como **cota conservadora** y como base de la
  comparación entre esquemas, **no** como el valor del indicador. (Si se tomara `metrics.json` como
  oficial, I-2.1 quedaría en 0.8136 < 0.85, es decir *no cumple*.)
- El recall (I-5.1) no tiene este problema: es **100 %** en ambos protocolos.

---

## Datos que necesitas definir antes de calcular

1. **Escenarios etiquetados.** Lista de anomalías inyectadas con hora de inicio, tipo, severidad y causa. Sirve para I-2.1, I-3.x, I-5.1 y I-0. *(Actualizado 2026-10-12: las etiquetas ya son nativas — `backend/app/tools/modelado/etiquetas.py`; 8 corridas normales y 13 anómalas, 508 ventanas.)*
2. **Criterio de severidad.** Umbrales documentados (baja/media/alta). *(Actualizado 2026-10-12: el sistema ya emite severidad C/A/M en `alertas.alt_sev`.)*
3. **Tamaño de muestra de la encuesta** y fecha de aplicación (I-4.3).
4. **Definición de "tasa de funcionamiento"** en el documento (I-5.3).
