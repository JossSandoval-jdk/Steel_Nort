# Fase de evaluación (CRISP-DM 5) — SteelNort

**Fecha:** 2026-10-15  
**Producto:** sistema inteligente de detección de anomalías de rendimiento en el OLTP de Steel Nort.  
**Modelo desplegado:** `ENSEMBLE_LOF_ELL` (LOF + Elliptic Envelope), 25 variables, ventana de 10 s, umbral **q01**.

Esta carpeta es la evidencia **visible** de la fase de evaluación: comparación de modelos, experimentos, tablas, gráficos, validación del candidato, análisis de errores, métricas y pruebas de carga (modelo y web).

Las cifras salen de artefactos del repositorio, no de estimaciones. La fuente oficial del F1 y del recall es `backend/app/tools/output/modelado/indicadores/honesto.json` (dejar-una-corrida-fuera + normalización por corrida). El test global `validacion/metrics.json` es **legacy** y se cita solo como cota conservadora y como base de la comparación entre esquemas.

| Documento | Contenido |
|---|---|
| [Comparación y experimentos](comparacion_y_experimentos.md) | 7 esquemas, 3 experimentos, tablas y gráficos |
| [Validación del candidato y errores](validacion_candidato_y_errores.md) | Por qué LOF+ELL, FN/FP, robustez, tipo y diagnóstico |
| [Carga: 1 usuario vs. sobrecarga (modelo y web)](carga_modelo_y_web.md) | Carga legítima vs. fallo; latencia de la API |
| [Gráficos](graficos/) | PNG listos para la tesis / defensa |

La evidencia de **cumplimiento de indicadores** (I-0 … I-5.4) está en [`docs/evidencia_indicadores/`](../evidencia_indicadores/README.md).

---

## Qué se evaluó

1. **Detección** (¿hay anomalía?): F1, recall, FPR, estabilidad por semilla.  
2. **Diagnóstico** (¿qué tipo y con qué variables?): Top-1/Top-2, coincidencia de huella, severidad.  
3. **Operación** (¿sirve en la web?): latencia de inferencia y de endpoints, tasa de pruebas, disponibilidad.  
4. **Carga** (¿un usuario está bien y diez saturan y confunden al detector?): corridas `normal_baja` / `normal_media` / `normal_alta` y escenarios `carga*`.

## Resultado en una frase

El candidato **ENSEMBLE_LOF_ELL** cumple F1 ≥ 85 % y recall ≥ 85 % en el protocolo honesto (F1 **0.9639**, recall **13/13**). La carga de usuarios *legítima* no debe tratarse como fallo: sin normalizar por corrida una captura de carga baja se alerta al 100 %; con el protocolo de producción el FPR por corrida sana es **0 %**.

![Validación del candidato](graficos/candidato_honesto_vs_global.png)
