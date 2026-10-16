# Hallazgos de validación — sistema de anomalías v2

Fecha: 2026-10-11
Scripts: `modelado/indicadores/01_validar_honesto.py`, `modelado/etiquetas.py` (nuevos)
Salidas: `output/modelado/indicadores/{honesto.json, etiquetas.json}`

> **Nota (2026-10-13):** las rutas de este documento se actualizaron al reordenar los scripts en
> `modelado/` (01-04), `modelado/experimental/` (01-03) y `modelado/indicadores/` (01-10).
> El contenido y las cifras no cambiaron.

Resumen en una línea: **los números que mostrábamos (100 %, 81 %) no valen: las
etiquetas estaban mal y todo se confunde con el efecto de captura. La evaluación
honesta da desempeño modesto en crudo y bueno solo si se normaliza por corrida;
el `ENSEMBLE_Z` actual es el peor y se reemplaza por `LOF + Elliptic`.**

---

## 1. Cómo se etiquetaba (y por qué está mal)

El pipeline ya etiqueta bien cada corrida: `origen.json` → `es_carga_normal`,
guardado en el dataset como `etiqueta_manual`. **La validación lo ignoraba** y
armaba el ground truth solo desde `anomalias/<corrida>/anomalias_timeline.csv`
(función `marcar_fault`). Resultado:

| corridas de test | ventanas | etiqueta vieja | realidad |
|---|---|---|---|
| `11`, `6`, `carga5`, `carga6`, `carga11`, `carga12` | 155 | falla | falla sintética (timeline) |
| `anomalia_live_202610_*` (6) | **322** | **normal** | **anomalía declarada** (`es_carga_normal: false`) |
| `carga3` | 31 | normal | anomalía declarada; su timeline no engancha con sus ventanas |

Problemas concretos:
- Las corridas **live no tienen timeline** → `marcar_fault` las cuenta como
  sanas, aunque su `origen.json` diga que **no** son carga normal. El modelo "se
  equivoca" (falso positivo) justo cuando acierta.
- **`carga3`** tiene timeline pero con otra fecha que sus ventanas → su falla se
  perdía.
- El test **no tiene ninguna corrida sana**: sus 508 ventanas son todas anomalía.

## 2. Corrección nativa de etiquetas

Nuevo módulo `modelado/etiquetas.py`, fuente única de ground truth:
- Etiqueta por corrida = la nativa del dataset (`etiqueta_manual`).
- Ventana = falla si su corrida es anomalía (timeline que cruza, o corrida
  entera si no hay timeline usable, como las live y `carga3`).

Con esto: **8 corridas normales** (entrenamiento) y **13 anómalas**; las 508
ventanas de test quedan como anomalía. Lo consume `01_validar_honesto.py` y
queda registrado en `output/modelado/indicadores/etiquetas.json`. `03_validar_candidato.py` se
mantiene solo para comparar con v1 (su `marcar_fault` es la fuente incompleta).

## 3. Efecto corrida (lo que confunde todo)

- Los positivos (fallas) y los negativos están en **corridas distintas** →
  nunca se compara "falla vs normal" dentro de la misma captura.
- **17 de 25 variables separan dos corridas normales con AUC ≥ 0.90.**
  Cualquier modelo puede "detectar" el salto de captura, no la falla.
- Por eso el protocolo "web" daba **F1 = 1.000** (falso) y el de v1 **0.81**
  (inflado).

## 4. Evaluación honesta

Protocolo:
- **FPR**: dejar-una-corrida-fuera entre las normales (¿alerta en una corrida
  sana que no vio?).
- **TPR**: modelo entrenado **solo con normales**, aplicado a cada anomalía.
- Variantes: **CRUDO** y **NORMALIZADO por corrida** (resta la mediana del run).

### CRUDO — no sirve para producción

| esquema | FPR corrida | TPR corrida | FPR ventana | F1 |
|---|---|---|---|---|
| ISOLATION_FOREST | 0.375 | 0.923 | 0.355 | 0.829 |
| COPOD | 0.000 | 0.615 | 0.063 | 0.515 |
| LOF | 0.250 | 1.000 | 0.220 | 0.903 |
| OCSVM | 0.500 | 1.000 | 0.530 | 0.847 |
| ELLIPTIC | 0.125 | 1.000 | 0.138 | 0.920 |
| ENSEMBLE_Z (producción) | 0.125 | 0.769 | 0.172 | 0.748 |
| ENSEMBLE_LOF_ELL | 0.125 | 1.000 | 0.184 | 0.935 |

### NORMALIZADO por corrida — la clave (q01)

| esquema | FPR corrida | TPR corrida | FPR ventana | TPR ventana | F1 |
|---|---|---|---|---|---|
| ISOLATION_FOREST | 0.00 | 0.38 | 0.000 | 0.434 | 0.474 |
| COPOD | 0.00 | 0.46 | 0.020 | 0.499 | 0.470 |
| LOF | 0.00 | 1.00 | 0.060 | 0.867 | 0.829 |
| OCSVM | 0.12 | 1.00 | 0.280 | 0.958 | 0.871 |
| ELLIPTIC | 0.00 | 0.92 | 0.074 | 0.830 | 0.906 |
| **ENSEMBLE_Z (producción)** | **0.00** | **0.38** | 0.010 | 0.453 | **0.435** |
| **ENSEMBLE_LOF_ELL** | **0.00** | **1.00** | **0.027** | **0.926** | **0.964** |
| LOF+ELLIPTIC+OCSVM | 0.00 | 1.00 | 0.028 | 0.932 | 0.965 |
| ISO+LOF+ELLIPTIC | 0.00 | 1.00 | 0.024 | 0.916 | 0.961 |

### Verificación del TPR corrida = 1.00 (LOF solo)

Auditoría por corrida (normalizado, q01):

| corrida | LOF solo | LOF+ELL |
|---|---|---|
| `11` | 100 % | 100 % |
| `6` | 92 % | 92 % |
| `carga5` | 92 % | 92 % |
| `carga6` | 100 % | 100 % |
| `carga11` | 74 % | 74 % |
| `carga12` | **59 %** | 63 % |
| `carga3` | **52 %** | 84 % |
| live `Diag_B/C/Eventos/Live/Prueba` (5) | 100 % | 100 % |
| live `Servidor_Negocio` | **57 %** | 99 % |

TPR corrida: **LOF solo = 13/13, LOF+ELL = 13/13**, `ENSEMBLE_Z` = 5/13.

Lectura honesta del "100 %":
- "13 de 13" significa *"la corrida no se comporta como una normal"* en la
  mayoría de sus ventanas — **no** *"identifiqué el instante exacto de la
  falla"*. No hay ventanas sanas dentro de corridas anómalas que permitan
  validar localización temporal.
- **LOF solo ya logra 13/13 sin Elliptic**: 92–100 % en las sintéticas fáciles,
  pero pasa justo de 50 % en las difíciles (52–59 %). Elliptic es lo que
  "completa" `carga3`, `carga12` y `Servidor_Negocio`.
- **Artefacto de Elliptic a controlar**: su covarianza no es de rango completo
  y su `decision_function` explota a ~-10⁹ en las live (z de -millones) → infla
  el F1 por ventana (0.964). Esos márgenes no están calibrados: valen para
  decidir con umbral, no para presumir la magnitud.
- **Robustez de LOF (tuning de k, normalizado, q01):** k=10 → F1 0.915 /
  fpr_v 0.078; k=15 → 0.870 / 0.043; k=20 → 0.829 / 0.060; k≥30 pierde
  corridas (11–12/13). LOF es determinista (no aplica semillas).
- El **FPR es el guardián honesto** de todo esto: normales fuera de
  entrenamiento → ~0.0 % ventanas en `ENSEMBLE_Z`, 2.7 % en LOF+ELL,
  6–8 % en LOF solo.

## 5. Conclusiones

1. **Sin normalizar por corrida, nada es desplegable**: el modelo marca como
   anómalas entre 12 % y 50 % de corridas sanas que no vio.
2. **Normalizar por corrida es el arreglo principal**: baja la falsa alarma a
   ~0 % a nivel corrida, manteniendo la detección.
3. **El `ENSEMBLE_Z` de producción es el peor**: con normalización detecta solo
   **38 %** de las anomalías (se le escapan 8 de 13) a q01. Su F1 no es confiable.
4. **`LOF + Elliptic` es el mejor honesto**: 100 % de las corridas anómalas
   detectadas y 2.7 % de falsa alarma por ventana en sanas. El 3-er modelo
   (OCSVM) no aporta (+0.001) y complica; se elige el par.
5. `q10` empeora todo (más falsa alarma). El punto utilizable es `q01`.

## 6. Cambios aplicados

- `modelado/etiquetas.py` (nuevo): ground truth nativo.
- `modelado/indicadores/01_validar_honesto.py`: usa la etiqueta nativa y rankea ensambles.
- `modelado/04_exportar_produccion.py` (nuevo): bundle de producción con el
  ensemble elegido en `output/modelado/produccion/` (scaler, features, ISO, LOF,
  ELLIPTIC, train pkl, meta).
- `app/tools/motor/detector.py`: ensamble generalizado (ISO/COPOD/LOF/ELLIPTIC).
  Autoelige **LOF+ELLIPTIC** si están sus modelos, si no **LOF solo**, si no
  ISO+COPOD, si no ISO. Se fuerza con `STEELNORT_ENSEMBLE` (`LOF_ELL` / `LOF` /
  `Z` / `ISO`).
- `modelado/indicadores/02_verificar_detector.py`: compara ISO/Z/LOF_ELL sobre dos
  orígenes (el desplegado y `produccion/`) y avisa cuando no se puede forzar el
  modo pedido (p. ej. LOF+ELL no existe en los artefactos v1).

Para desplegar el modelo nuevo hay que apuntar `ML_ARTIFACTS_DIR` (y
`ML_TRAIN_PKL`) al directorio `produccion/`. **Actualizado (2026-10-13):** ya está
hecho — `backend/.env` apunta a
`D:\SteelNort_web_v2\backend\app\tools\output\modelado\produccion`, así que el
detector desplegado es `ENSEMBLE_LOF_ELL` (las líneas de v1 quedan comentadas en
el `.env`).

## 7. Recomendaciones

**Datos / etiquetas (prioridad):**
- Mantener el ground truth nativo (corridas live como anomalías) y arreglar la
  captura/timeline de `carga3`.
- Sumar corridas sanas y anómalas (hoy 8 y 13) y **varias capturas por caso**
  para medir variabilidad.
- Capturar cobertura real por tabla (hoy casi vacía) si se quiere causa raíz.

**Modelo:**
- Adoptar **normalización por corrida** (baseline móvil en producción).
- Reemplazar `ENSEMBLE_Z` por **LOF + Elliptic** (bundle ya generado). Decisión
  tomada 2026-10-11: **se mantiene LOF+ELL** (mejor FPR 2.7 % y F1 honesto);
  LOF solo queda disponible vía `STEELNORT_ENSEMBLE=LOF` sin regenerar el
  bundle si se prioriza simplicidad sobre falsa alarma.
- No publicar los % actuales (ni el 100 % ni el 81 %). Usar esta tabla.
- No reportar el F1 0.964 ni los z de Elliptic como "precisión de ventana":
  publicar TPR corrida (13/13) por categoría (sintética/live) con el caveat de
  localización temporal no validada.

## 8. Reproducir

```
cd backend/app/tools/modelado
python 04_exportar_produccion.py          # -> output/modelado/produccion/
cd indicadores
python 01_validar_honesto.py              # -> output/modelado/indicadores/{honesto,etiquetas}.json
```

> `honesto.json` es el resultado válido; no reemplaza `metrics.json` (legacy).

## 9. Bug del bundle corregido (escalador) + tiempos

Al cronometrar el bundle nuevo por la **ruta viva** (`/telemetria/push` ->
`detector.evaluar`) apareció un fallo que la verificación previa no veía
(llamaba `_score_ensamble` directo, sin escalar):

```
IndexError: index 26 is out of bounds for axis 0 with size 25
  detector._escalar -> self._scaler.mean_[pos]
```

Causa: `04_exportar_produccion.py` guardaba un **sub-escalador de 25** columnas
(solo las variables del modelo), pero `_escalar` indexa el escalador con la
posición de cada variable dentro de las **features del train** (69). El
contrato del detector es `len(scaler) == len(features)` (v1: 54 = 54).

Corrección (opción B, sin tocar código de producción): guardar el escalador
**completo** (`art["scaler"]`, 69) y regenerar el bundle. Umbrales idénticos
(q01 = -3.557): el ensemble es determinista.

Se agregó a `02_verificar_detector.py` una prueba de la **ruta viva**
(`verificar_ruta_viva`) por origen, para cazar este tipo de fallo.

Tiempos medidos (SQL Server **local**, detector real, `persistir_anomalia` con
`rollback` para no dejar rastro; sin informe/captura en disco):

| Etapa | desplegado (v1, `ENSEMBLE_Z`) | bundle corregido (`ENSEMBLE_LOF_ELL`) |
|---|---|---|
| `detector.evaluar` (ML + zonal) | 30.1 ms | **9.6 ms** |
| `motor_reglas.evaluar` (sin eventos) | ~0.0 ms | ~0.0 ms |
| variables + resumen diagnóstico | 0.08 ms | 0.08 ms |
| `persistir_anomalia` (BD, rollback) | 461.6 ms | 461.6 ms |
| **Total detección + diagnóstico** | **~0.5 s** | **~0.47 s** |

Lectura: el cómputo de diagnóstico es despreciable (~10-30 ms); el peso está en
la **escritura en BD** (~0.46 s). Frente a la latencia del sistema (ventana
70 s + consenso 14-21 s), los ~0.5 s del diagnóstico son irrelevantes.
