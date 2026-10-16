# Indicadores por objetivo — Steel Nort (Sistema inteligente para anomalías de rendimiento OLTP)

> ⚠️ **Documento superado.** La versión vigente es [`Indicadores_v2.md`](Indicadores_v2.md), que
> agrega la columna **Valor medido / estado** con cifras tomadas de los artefactos del repo
> (no de estimaciones). Este archivo se conserva como referencia del mapeo original de objetivos.

> Los indicadores marcados **[Tabla III]** salen del mapeo de objetivos del documento.
> Los marcados **[Propuesto]** los agregué para cerrar vacíos (definición faltante o requisito sin indicador). Puedes quitarlos.

## Resumen

| Cód. | Objetivo | Indicador | Meta | Origen |
|---|---|---|---|---|
| I-0 | General | Reducción del tiempo de detección de anomalías (pre vs. post) | Diferencia significativa (p < 0.05) | [Propuesto] |
| I-1.1 | OE1 | Volumen de datos extraídos | Sin meta fija (reportar) | [Tabla III] |
| I-1.2 | OE1 | Índice de calidad de datos | ≥ 95 % | [Tabla III] |
| I-2.1 | OE2 | F1-Score de detección | ≥ 85 % | [Tabla III] |
| I-2.2 | OE2 | Variables con correlación relevante | \|r\| ≥ 0.6 | [Tabla III] |
| I-3.1 | OE3 | Precisión de clasificación por tipo | ≥ 90 % | [Tabla III] |
| I-3.2 | OE3 | Coincidencia de severidad | ≥ 90 % | [Tabla III] |
| I-3.3 | OE3 | Efectividad del diagnóstico | ≥ 85 % | [Tabla III] |
| I-4.1 | OE4 | Cumplimiento de requisitos (RF + RNF) | 100 % | [Tabla III] |
| I-4.2 | OE4 | Tiempo de respuesta de dashboard y alertas | ≤ 3 s | [Tabla III] |
| I-4.3 | OE4 | Satisfacción de usuarios | ≥ 80 % | [Tabla III] |
| I-5.1 | OE5 | Recall de detección | ≥ 85 % | [Tabla III] |
| I-5.2 | OE5 | Tiempo de respuesta promedio en operaciones principales | ≤ 3 s | [Tabla III] |
| I-5.3 | OE5 | Tasa de funcionamiento | ≥ 90 % | [Tabla III] |
| I-5.4 | OE5 | Disponibilidad en horario del OLTP | ≥ 95 % | [Propuesto] (RNF3) |

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

> **Nota de implementación (fase actual):** el detector desplegado es el
> **ENSEMBLE_Z** = IsolationForest + COPOD con score combinado por z-score
> (`app/ml/ensamble_z.py`), no IsolationForest aislado. El F1 de este
> indicador (y el recall de I-5.1) se miden sobre el ENSEMBLE_Z en
> **hold-out por corrida** con `nucleo/modeling/experimental/validar_candidato.py`
> → `training/output/modelado/deteccion/validacion/`. El snippet anterior es
> el ejemplo ilustrativo de la fórmula.

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

> **Nota:** reporte vivo = `training/output/modelado/correlacion/variables_correlacion.csv`,
> generado por `nucleo/modeling/02_correlacion.py` con
> `UMBRAL_CORRELACION_INDICADOR = 0.6`. El `UMBRAL_CORRELACION = 0.85` es el
> umbral de *poda* de variables (otro parámetro) y no sustituye a este.

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

> **Nota:** se mide sobre el ENSEMBLE_Z en el mismo hold-out por corrida de
> I-2.1 (`validar_candidato.py`, stage `metrics`).

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

## Datos que necesitas definir antes de calcular

1. **Escenarios etiquetados.** Lista de anomalías inyectadas con hora de inicio, tipo, severidad y causa. Sirve para I-2.1, I-3.x, I-5.1 y I-0.
2. **Criterio de severidad.** Umbrales documentados (baja/media/alta).
3. **Tamaño de muestra de la encuesta** y fecha de aplicación (I-4.3).
4. **Definición de "tasa de funcionamiento"** en el documento (I-5.3).
