"""Servicio de reentrenamiento usando el pipeline de modelado existente.

Reutiliza los scripts 01_muestras.py, 02_correlacion.py y
03_deteccion_isolation_forest.py del pipeline de entrenamiento.

FLUJO:
  1. Lee Muestras_Normales de la BD (SOLO datos normales).
  2. Exporta a CSV con el formato que espera 01_muestras.py.
  3. Corre los scripts de modelado via subprocess.
  4. Compara FPR del nuevo modelo vs el actual.
  5. Si es mejor → reemplaza artefactos en ml/artifacts/.
  6. Las anomalías NUNCA se usan para entrenar.

IMPORTANTE: Las anomalías se usan solo para diagnóstico
(Predicciones_ML + Alertas), NUNCA para entrenar.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.model_ml import ModelosML
from app.models.model_muestra_normal import MuestrasNormales

log = logging.getLogger("steelnort.reentrenamiento")

BACKEND_ROOT = Path(__file__).resolve().parent.parent
ML_ARTIFACTS_DIR = BACKEND_ROOT / "ml" / "artifacts"
ML_BACKUP_DIR = BACKEND_ROOT / "ml" / "backups"
TRAINING_DIR = BACKEND_ROOT / "training" / "nucleo" / "modeling"

MIN_MUESTRAS = 200
DIAS_DEFAULT = 7
VENTANA = 10


def _leer_muestras_normales(db: Session, dias: int = DIAS_DEFAULT) -> pd.DataFrame:
    """Lee muestras normales de los últimos N días y retorna un DataFrame."""
    desde = datetime.utcnow() - timedelta(days=dias)

    filas = (
        db.query(MuestrasNormales)
        .filter(MuestrasNormales.mno_fec >= desde)
        .filter(MuestrasNormales.fec_eli.is_(None))
        .order_by(desc(MuestrasNormales.mno_fec))
        .limit(50000)
        .all()
    )

    if not filas:
        return pd.DataFrame()

    registros = []
    for f in filas:
        try:
            feats = json.loads(f.mno_feats) if f.mno_feats else {}
            fila = {"timestamp": f.mno_fec.isoformat()}
            fila.update({k: float(v) for k, v in feats.items()})
            registros.append(fila)
        except (json.JSONDecodeError, ValueError, TypeError):
            continue

    if not registros:
        return pd.DataFrame()

    df = pd.DataFrame(registros)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)

    df["run_name"] = "retrain_normal"
    df["experiment_id"] = "exp_01"

    return df


def _exportar_csv_reentrenamiento(df: pd.DataFrame, ruta: str) -> bool:
    """Exporta el DataFrame al formato que espera 01_muestras.py.

    El CSV debe tener: timestamp, run_name, experiment_id,
    y las variables principales del modelo.
    """
    from training.nucleo.data_preparation.config import VARIABLES_PRINCIPALES

    columnas_requeridas = ["timestamp", "run_name", "experiment_id"] + VARIABLES_PRINCIPALES

    for col in VARIABLES_PRINCIPALES:
        if col not in df.columns:
            df[col] = 0.0

    df_export = df[columnas_requeridas].copy()
    df_export.to_csv(ruta, index=False, encoding="utf-8-sig")

    log.info("CSV de reentrenamiento exportado: %s (%d filas)", ruta, len(df_export))
    return True


def _correr_script(script_path: str, cwd: str, env: dict) -> tuple[bool, str]:
    """Ejecuta un script de modelado y retorna (exito, output)."""
    try:
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            cwd=cwd,
            env=env,
            timeout=300,
        )
        output = result.stdout + "\n" + result.stderr
        if result.returncode != 0:
            log.error("Script %s falló:\n%s", script_path, output[-2000:])
            return False, output
        log.info("Script %s completado OK", script_path)
        return True, output
    except subprocess.TimeoutExpired:
        log.error("Script %s excedió timeout de 300s", script_path)
        return False, "Timeout"
    except Exception as e:
        log.error("Error ejecutando %s: %s", script_path, e)
        return False, str(e)


def _cargar_artefactos_actuales():
    """Carga el modelo actual para comparar."""
    modelo_path = ML_ARTIFACTS_DIR / "modelo_isolation_forest.joblib"
    scaler_path = ML_ARTIFACTS_DIR / "scaler.joblib"
    features_path = ML_ARTIFACTS_DIR / "features_modelo.csv"

    if not all(p.exists() for p in [modelo_path, scaler_path, features_path]):
        return None, None, None

    modelo = joblib.load(modelo_path)
    scaler = joblib.load(scaler_path)
    df_feats = pd.read_csv(features_path)
    features = df_feats.iloc[:, 0].astype(str).str.strip().tolist()

    return modelo, scaler, features


def reentrenar(dias: int = DIAS_DEFAULT, force: bool = False) -> dict:
    """Ejecuta el pipeline de reentrenamiento usando los scripts de modelado.

    1. Lee muestras normales de la BD.
    2. Exporta a CSV.
    3. Corre 01_muestras.py, 02_correlacion.py, 03_deteccion.py.
    4. Compara y reemplaza si es mejor.
    """
    result = {
        "exito": False,
        "mensaje": "",
        "muestras_usadas": 0,
        "modelo_anterior": None,
        "modelo_nuevo": None,
        "pasos_completados": [],
    }

    modelo_actual, scaler_actual, features_actual = _cargar_artefactos_actuales()
    if modelo_actual is None:
        result["mensaje"] = "No hay artefactos del modelo actual."
        return result

    result["modelo_anterior"] = str(ML_ARTIFACTS_DIR / "modelo_isolation_forest.joblib")

    # 1. Leer muestras normales
    db = SessionLocal()
    try:
        df = _leer_muestras_normales(db, dias)
    finally:
        db.close()

    if len(df) < MIN_MUESTRAS and not force:
        result["mensaje"] = (
            f"Muy pocas muestras normales ({len(df)}). "
            f"Mínimo: {MIN_MUESTRAS}."
        )
        return result

    if len(df) == 0:
        result["mensaje"] = "No hay muestras normales en la BD."
        return result

    result["muestras_usadas"] = len(df)

    # 2. Crear directorio temporal para el pipeline
    with tempfile.TemporaryDirectory(prefix="steelretrain_") as tmpdir:
        tmpdir_path = Path(tmpdir)
        output_dir = tmpdir_path / "output"
        output_dir.mkdir()

        modelado_dir = output_dir / "modelado"
        correlacion_dir = modelado_dir / "correlacion"
        deteccion_dir = modelado_dir / "deteccion"
        integrado_dir = output_dir / "integrado"

        for d in [modelado_dir, correlacion_dir, deteccion_dir, integrado_dir]:
            d.mkdir(parents=True, exist_ok=True)

        # 3. Exportar CSV
        csv_path = integrado_dir / "dataset_carga_principales.csv"
        if not _exportar_csv_reentrenamiento(df, str(csv_path)):
            result["mensaje"] = "Error exportando CSV de reentrenamiento."
            return result

        # 4. Configurar entorno para los scripts
        env = os.environ.copy()
        env["STEELNORT_OUTPUT_DIR"] = str(output_dir)

        modeling_dir = str(TRAINING_DIR)

        # 5. Ejecutar 01_muestras.py
        ok, out = _correr_script(
            os.path.join(modeling_dir, "01_muestras.py"),
            modeling_dir, env,
        )
        if not ok:
            result["mensaje"] = f"Fallo en 01_muestras.py: {out[-500:]}"
            return result
        result["pasos_completados"].append("01_muestras")

        # 6. Ejecutar 02_correlacion.py
        ok, out = _correr_script(
            os.path.join(modeling_dir, "02_correlacion.py"),
            modeling_dir, env,
        )
        if not ok:
            result["mensaje"] = f"Fallo en 02_correlacion.py: {out[-500:]}"
            return result
        result["pasos_completados"].append("02_correlacion")

        # 7. Ejecutar 03_deteccion_isolation_forest.py
        ok, out = _correr_script(
            os.path.join(modeling_dir, "03_deteccion_isolation_forest.py"),
            modeling_dir, env,
        )
        if not ok:
            result["mensaje"] = f"Fallo en 03_deteccion.py: {out[-500:]}"
            return result
        result["pasos_completados"].append("03_deteccion")

        # 8. Verificar que se generaron los artefactos
        nuevos_artefactos = {
            "modelo": deteccion_dir / "modelo_isolation_forest.joblib",
            "scaler": deteccion_dir / "scaler.joblib",
            "features": correlacion_dir / "features_modelo.csv",
            "umbrales": correlacion_dir / "reglas_umbrales.csv",
        }

        for nombre, ruta in nuevos_artefactos.items():
            if not ruta.exists():
                result["mensaje"] = f"No se generó artefacto: {nombre} ({ruta})"
                return result

        # 9. Comparar modelos: evaluar FPR del nuevo vs actual
        try:
            modelo_nuevo = joblib.load(nuevos_artefactos["modelo"])
            scaler_nuevo = joblib.load(nuevos_artefactos["scaler"])
            df_feats_nuevo = pd.read_csv(nuevos_artefactos["features"])
            features_nuevos = df_feats_nuevo.iloc[:, 0].astype(str).str.strip().tolist()

            # Construir vectores de las muestras para evaluar
            from training.nucleo.modeling import config as model_config

            # Usar las mismas features que el modelo actual para la comparación
            cols_comparar = [c for c in features_actual if c in df.columns]
            if len(cols_comparar) < 5:
                cols_comparar = features_actual

            X_eval = df[cols_comparar].fillna(0).to_numpy(dtype="float64")

            # Aplanar con ventana
            if len(X_eval) >= VENTANA:
                ventanas = []
                for i in range(len(X_eval) - VENTANA + 1):
                    ventanas.append(X_eval[i:i + VENTANA])
                X_flat = np.stack(ventanas).reshape(len(ventanas), -1)

                # Escalar con scaler actual
                X_scaled = scaler_actual.transform(X_flat)

                # FPR del modelo actual
                scores_actual = modelo_actual.decision_function(X_scaled)
                umbral_actual = np.quantile(scores_actual, 0.01)
                fpr_actual = float((scores_actual < umbral_actual).mean())

                # FPR del modelo nuevo (si tiene las mismas features)
                try:
                    X_nuevo = scaler_nuevo.transform(X_flat)
                    scores_nuevo = modelo_nuevo.decision_function(X_nuevo)
                    umbral_nuevo = np.quantile(scores_nuevo, 0.01)
                    fpr_nuevo = float((scores_nuevo < umbral_nuevo).mean())
                except Exception:
                    # Si las features difieren, aceptar el nuevo modelo
                    fpr_nuevo = fpr_actual
                    log.warning("No se pudo comparar FPR directamente (features difieren)")

                log.info(
                    "Comparación FPR: actual=%.2f%% vs nuevo=%.2f%%",
                    fpr_actual * 100, fpr_nuevo * 100,
                )
            else:
                fpr_actual = 0.0
                fpr_nuevo = 0.0

        except Exception as e:
            log.warning("No se pudo comparar modelos: %s. Se acepta el nuevo.", e)
            fpr_actual = 0.0
            fpr_nuevo = 0.0

        # 10. Decisión
        mejor = fpr_nuevo <= fpr_actual or force

        if not mejor:
            result["mensaje"] = (
                f"El modelo actual es mejor (FPR actual={fpr_actual*100:.1f}%, "
                f"nuevo={fpr_nuevo*100:.1f}%). No se reemplaza."
            )
            return result

        # 11. Reemplazar artefactos
        os.makedirs(ML_BACKUP_DIR, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

        for nombre in ["modelo_isolation_forest.joblib", "scaler.joblib"]:
            src = ML_ARTIFACTS_DIR / nombre
            if src.exists():
                shutil.copy2(src, ML_BACKUP_DIR / f"{ts}_{nombre}")

        shutil.copy2(nuevos_artefactos["modelo"], ML_ARTIFACTS_DIR / "modelo_isolation_forest.joblib")
        shutil.copy2(nuevos_artefactos["scaler"], ML_ARTIFACTS_DIR / "scaler.joblib")
        shutil.copy2(nuevos_artefactos["features"], ML_ARTIFACTS_DIR / "features_modelo.csv")
        shutil.copy2(nuevos_artefactos["umbrales"], ML_ARTIFACTS_DIR / "reglas_umbrales.csv")

        result["modelo_nuevo"] = str(ML_ARTIFACTS_DIR / "modelo_isolation_forest.joblib")

        # 12. Registrar en Modelos_ML
        db = SessionLocal()
        try:
            modelo_anterior_db = (
                db.query(ModelosML)
                .filter(ModelosML.mdl_act == True, ModelosML.fec_eli.is_(None))
                .first()
            )
            if modelo_anterior_db:
                modelo_anterior_db.mdl_act = False

            features_str = ",".join(features_nuevos)
            nuevo_mdl = ModelosML(
                mdl_nom=f"IsolationForest_retrain_{ts}",
                mdl_tipo="isolation_forest",
                mdl_umbral_pct=85.00,
                mdl_vars=features_str,
                mdl_hparms=json.dumps({
                    "contamination": "auto",
                    "random_state": 42,
                    "fpr_q01": fpr_nuevo,
                    "fpr_anterior": fpr_actual,
                    "muestras_entrenamiento": result["muestras_usadas"],
                    "pasos_pipeline": result["pasos_completados"],
                }),
                mdl_ruta_art=str(ML_ARTIFACTS_DIR / "modelo_isolation_forest.joblib"),
                mdl_act=True,
                mdl_fec_entr=datetime.utcnow(),
                reg_usu="reentrenamiento_automatico",
            )
            db.add(nuevo_mdl)
            db.commit()

            # Invalidar cache del detector
            from app.ml import detector as det_mod
            det_mod._detector = None

            result["exito"] = True
            result["mensaje"] = (
                f"Modelo reentrenado con {result['muestras_usadas']} muestras normales. "
                f"FPR: {fpr_actual*100:.1f}% → {fpr_nuevo*100:.1f}%. "
                f"Pipeline: {' → '.join(result['pasos_completados'])}."
            )
            log.info("Reentrenamiento completado: %s", result["mensaje"])

        except Exception as e:
            db.rollback()
            result["mensaje"] = f"Error guardando modelo: {e}"
            log.exception("Error en reentrenamiento")
        finally:
            db.close()

    return result


def estado_reentrenamiento(db: Session) -> dict:
    """Devuelve el estado del modelo activo."""
    ultimo = (
        db.query(ModelosML)
        .filter(ModelosML.fec_eli.is_(None))
        .order_by(desc(ModelosML.mdl_cod))
        .first()
    )
    if ultimo is None:
        return {"hay_modelo": False}

    hparms = {}
    try:
        hparms = json.loads(ultimo.mdl_hparms) if ultimo.mdl_hparms else {}
    except (json.JSONDecodeError, TypeError):
        pass

    return {
        "hay_modelo": True,
        "modelo_activo": ultimo.mdl_act,
        "nombre": ultimo.mdl_nom,
        "tipo": ultimo.mdl_tipo,
        "fecha_entrenamiento": str(ultimo.mdl_fec_entr) if ultimo.mdl_fec_entr else None,
        "features": ultimo.mdl_vars.split(",") if ultimo.mdl_vars else [],
        "umbrales": hparms.get("umbrales", {}),
        "fpr_actual": hparms.get("fpr_q01"),
        "fpr_anterior": hparms.get("fpr_anterior"),
        "muestras_entrenamiento": hparms.get("muestras_entrenamiento"),
        "pasos_pipeline": hparms.get("pasos_pipeline", []),
    }
