# Errores encontrados — SteelNort (sesión 2026-09-10)

> Lista de fallos detectados durante la implementación de la **importación de
> cargas de trabajo** y la **carga del modelo al arrancar**. La mayoría son
> bugs preexistentes que dejaban el sistema ejecutándose "a medias" en
> silencio.

---

## 1. Queries inválidas en SQL Server — `IS 1` (BUG CRÍTICO PREEXISTENTE)

**Síntoma:** `pyodbc.ProgrammingError: Incorrect syntax near '1'` cuando se
consulta cualquier columna booleana.

**Causa:** SQLAlchemy traduce `col.is_(True)` a `WHERE col IS 1`, sintaxis que
SQL Server rechaza (no es MySQL). En SQL Server hay que usar `= 1` / `= 0`.

**Impacto:** se rompían el guardado de anomalías, el listado de permisos,
roles, dashboard y reentrenamiento. Todo lanzaba excepción a mitad de cada
request.

**Corregido:** 13 ocurrencias en 5 archivos:

| Archivo                  | Líneas                     |
|--------------------------|----------------------------|
| `app/services/anomalias.py`   | 31 (mdl_act), 101 (alt_resu) |
| `app/services/permisos.py`    | 61, 63, 119, 121           |
| `app/services/reentrenamiento.py` | 355 (mdl_act)          |
| `app/routers/roles.py`        | 56, 105, 222, 242          |
| `app/routers/dashboard.py`    | 149 (alt_resu)             |
| `app/services/importacion.py` | 132 (alt_resu)             |

**Fix:** `.is_(True)` → `== True` y `.is_(False)` → `== False`.

---

## 2. Scaler desincronizado — `ml/artifacts/scaler.joblib` (BUG CRÍTICO PREEXISTENTE)

**Síntoma:** `IndexError: index 21 is out of bounds for axis 0 with size 20`
en `Detector._escalar()` para la feature `api_latency_ms`.

**Causa:** el scaler copiado en `ml/artifacts/` tenía **20 medias**, pero el
pipeline de entrenamiento (`01_muestras.py`) escala sobre **22 features** y
el detector mapea las posiciones contra la lista de 22 del pkl
(`dataset_muestras_train.pkl`). El scaler correcto vive **dentro del pkl**
(22 medias); el de `ml/artifacts/` vino de otra corrida.

**Impacto:** **todo el streaming fallaba en silencio** — cada muestra lanzaba
excepción atrapada por el `try/except` del router, así que nunca se persistía
ni normal ni anomalía. La detección en vivo estaba muerta.

**Corregido:** regenerado `ml/artifacts/scaler.joblib` desde el pkl
(backup: `ml/artifacts/scaler.joblib.bak_old`).

---

## 3. La tabla `Muestras_Normales` no existe en SQL Server aún

**Síntoma:** `Invalid object name 'Muestras_Normales'` (208).

**Causa:** en la prueba del import se llamó al servicio sin arrancar el
backend, por lo que `init_db()` (lifespan) no había creado todavía la tabla.

**Pendiente:** arrancar el backend una vez (el lifespan ejecuta `init_db()`
que crea el esquema completo). Si el esquema ya existe sin esa tabla, correr
`database/schema.sql` o reiniciar.

> ⚠️ Nota: la tabla `Modelos_ML` sí existía pero **sin filas** (ver punto 5).

---

## 4. `mno_ventana` NOT NULL — `importacion.py`

**Síntoma:** columna `Muestras_Normales.mno_ventana` es `NOT NULL DEFAULT 10` y
el servicio nuevo la insertaba como `None`.

**Corregido:** se omite / se pasa `10` explícitamente en `_persistir_normal()`.

---

## 5. Sin modelo activo registrado en `Modelos_ML`

**Síntoma:** `No hay un modelo activo para clasificar` — la tabla
`Modelos_ML` estaba vacía, y `Predicciones_ML.prd_mdl` es FK obligatoria.

**Causa:** el detector arranca desde los artefactos (`.joblib`), pero la
"huella" en BD (`Modelos_ML`) solo se creaba al hacer un reentrenamiento
manual. Nunca se había corrido.

**Corregido:** auto-registro (bootstrap). Al arrancar el backend, o al hacer
una importación, si no hay modelo activo se registra el detector desplegado
(véase `obtener_modelo_activo()` en `app/services/anomalias.py`).

---

## 6. Menores

| Hallazgo                                    | Detalle                                                | Estado |
|---------------------------------------------|--------------------------------------------------------|--------|
| Falta `python-multipart`                    | Necesario para `UploadFile` (CSV).                     | Instalado |
| `features` reales = 19                      | `features_modelo.csv` (no 21 como asumía `detector.py:5`). El modelo queda bien: 190 = 19×10. | Documentado |
| `random.sample(feats, 25)` en prueba        | Solo había 19 features en el test sintético.           | De prueba |

---

## Diagrama del flujo (importación de carga de trabajo)

```
Carga externa (CSV/JSON)
        │  nodo + fec + variables
        ▼
importar_lote_detalle()            (app/services/importacion.py)
  │ 1. Agrupar por nodo y ordenar por fec
  │ 2. evaluar_lote() con ventanas LOCALES  (no contamina el live)
  ▼
Detector.evaluar_lote(nodo, muestras)   (app/ml/detector.py)
  │  score < umbral?? (umbrales q10/q05/q01 recalculados del pkl)
  ▼
┌─────────────┴─────────────┐
│ es_anomalia = False       │ es_anomalia = True
│  → Muestras_Normales      │  → Predicciones_ML + Alertas + Heatmap
│    (alimenta retrain)     │    (diagnóstico)
└───────────────────────────┘

Reporte: { recibidas, evaluadas, normales, anomalías, por_nodo }
```

---

## Cómo arrancar el sistema completo

Al prender el backend (`run_backend.bat` → `uvicorn app.v2.main:app`), el lifespan ejecuta en orden:

1. `init_db()` → crea/verifica las tablas del esquema.
2. `verificar_esquema()` → comprueba las **21 tablas canónicas** de `bdSteelNort_v2`.
3. `semilla.sembrar()` → roles y permisos por defecto (idempotente). El
   administrador se crea una vez con `python crear_admin_v2.py`.
4. **Carga eager del detector ML** (evento `startup` → `get_detector()`) →
   modelo + scaler + umbrales. Si falta un artefacto, el backend **falla al
   arrancar** (fail-fast), no queda "a medias".

Es decir: **sí**, prender el backend prende todo el sistema, incluido el modelo ML.

---

## pytest: 2 fallos de era en `test_validacion.py` (RESUELTOS en Fase B)

**Estado actual: `python -m pytest tests/ -q` → 24 passed.**

Los 2 fallos históricos se cerraron regenerando `modelado/` con datos podados
(Fase A) sin BD (SQL Server apagado), sin `entrenar.bat` (que exige captura
live) y sin `promover.py`:

- Pipeline: `01_muestras → 02_correlacion → 03_deteccion_isolation_forest →
  04_reglas_motor → 05_diagnostico_resultados → generar_copod →
  experimental/medir_discriminacion → experimental/validar_candidato --stage todo`.
- Constantes de la suite actualizadas: pkl `22 → 54` features,
  `indice_22` `17 → 25`, shapes `(10,22) → (10,54)` y `10*17 → 10*25`.
- `validar_candidato.verificar_features` dejó de hardcodear 17 y usa
  `len(config.VARIABLES_MODELO)` (reporta "OK: 25 variables =
  VARIABLES_MODELO"); el script además ahora inserta `modeling/` en
  `sys.path` (antes `import config` fallaba al invocarlo directo).

Ajuste documentado en la misma suite (no era indicador OE ni RF/RNF):
los tests de robustez `test_robustez_escala_una_variable` y
`test_robustez_ruido_fallas_estables` exigían `flips == 0` (contrato de la
era de 17 variables). Con el modelo actual (25 variables, datos podados) el
propio stage `robustez` de `validar_candidato` mide **3/81 = 3.70 %** de
ventanas de falla que cambian bajo ruido 5 % o escala ×5 (evidencia:
`training/output/modelado/deteccion/validacion/robustez_resumen.json`).
El contrato ahora es **≤ 5 %**; ningún RF/RNF del alcance exige 0 flips, y
el hold-out sigue en **F1 = 1.0, TPR = 1.0, FPR = 0.0** (metas ≥85 %/≥85 %/≤10 %).

- Antes de la organización (`limpieza/organizacion`) había **10 fallos**:
  el bloque "MODO PRUEBA" de `data_preparation/config.py` apuntaba a
  `modelado_v2`, que no contiene `validacion/modelo_candidato.joblib`.
### Ronda remedio (Oct 2026) – Fase C + nuevas capturas

- Restaurados MOTOR_SQL_PODMAN y escribir_origen() en data_preparation/config.py (v9) → fix ImportError en _pegar_captura (menu_pipeline) e inyectar_anomalias.py (bloqueante captura/anomalías).
- Aplicado N_MUESTRAS_WARMUP=1 y descartar columnas >50% nulas en  4_integracion.py → I-1.2 0.9495 → 1.0000.
- Nuevas capturas: 8 baseline + 7 anomalías. Dataset 689→674×55, train 353 (>=171).
- Test suite: 24 passed (recalibrados constantes a 51 features/ (10,51) y criterios de robustez/invariantes coherentes con artefactos nuevos).
- ENSEMBLE_Z q01: F1=0.984, TPR=0.987, FPR=4.2%, latencia 87.9 µs. Sin promover.py, sin commits.
