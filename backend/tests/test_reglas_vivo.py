"""Pruebas del motor de reglas en vivo (app/ml/reglas.py).

Verifica que cada regla R1-R7 dispare con el evento que le corresponde y que
la normalizacion XE (microsegundos -> milisegundos) sea la correcta. No toca
la base de datos ni los artefactos del modelado.

Ejecutar desde la raiz del backend:
    python -m pytest tests/test_reglas_vivo.py -q
"""

from app.ml import reglas


def _evento(**extra):
    base = {
        "event_name": "xe.sql_batch_completed",
        "timestamp": "2026-09-23 10:00:00.000",
        "session_id": 51,
        "duration": 0,
        "cpu_time": 0,
        "logical_reads": 0,
    }
    base.update(extra)
    return base


def _codigos(detecciones):
    return {d["regla"] for d in detecciones}


# ---------------------------------------------------------------------------
# Normalizacion
# ---------------------------------------------------------------------------
def test_normaliza_microsegundos_a_milisegundos():
    ev = reglas.normalizar_evento(_evento(duration=750000, cpu_time=250000,
                                          signal_duration=10000))
    assert ev["duration"] == 750.0
    assert ev["cpu_time"] == 250.0
    assert ev["signal_wait_time_ms"] == 10.0
    assert ev["event_name"] == "sql_batch_completed"


def test_espera_de_fondo_no_dispara():
    det = reglas.evaluar([_evento(event_name="xe.wait_info", wait_type="SLEEP_TASK",
                                   duration=5000000)])
    assert det == []


# ---------------------------------------------------------------------------
# R1 - I/O fisico
# ---------------------------------------------------------------------------
def test_r1_iolatch_duracion_alta():
    det = reglas.evaluar([_evento(event_name="xe.wait_info",
                                   wait_type="PAGEIOLATCH_SH", duration=600000)])
    assert "R1" in _codigos(det)


def test_r1_duracion_baja_no_dispara():
    det = reglas.evaluar([_evento(event_name="xe.wait_info",
                                   wait_type="PAGEIOLATCH_SH", duration=100000)])
    assert "R1" not in _codigos(det)


# ---------------------------------------------------------------------------
# R2 - bloqueos
# ---------------------------------------------------------------------------
def test_r2_lock_dispara():
    det = reglas.evaluar([_evento(event_name="xe.wait_info", wait_type="LCK_M_X",
                                   duration=200000)])
    assert "R2" in _codigos(det)


# ---------------------------------------------------------------------------
# R3 - CPU
# ---------------------------------------------------------------------------
def test_r3_scheduler_yield():
    det = reglas.evaluar([_evento(event_name="xe.wait_info",
                                   wait_type="SOS_SCHEDULER_YIELD", duration=100000)])
    assert "R3" in _codigos(det)


def test_r3_cpu_cercana_a_duracion():
    det = reglas.evaluar([_evento(duration=1000000, cpu_time=950000)])
    assert "R3" in _codigos(det)


def test_r3_cpu_baja_no_dispara():
    det = reglas.evaluar([_evento(duration=1000000, cpu_time=100000)])
    assert "R3" not in _codigos(det)


# ---------------------------------------------------------------------------
# R4 - tempdb
# ---------------------------------------------------------------------------
def test_r4_pagelatch_tempdb():
    det = reglas.evaluar([_evento(event_name="xe.wait_info", wait_type="PAGELATCH_EX",
                                   wait_resource="2:1:3", duration=200000)])
    assert "R4" in _codigos(det)


def test_r4_pagelatch_otra_pagina_no_dispara():
    det = reglas.evaluar([_evento(event_name="xe.wait_info", wait_type="PAGELATCH_EX",
                                   wait_resource="5:1:3", duration=200000)])
    assert "R4" not in _codigos(det)


# ---------------------------------------------------------------------------
# R5 - memoria y R6 - red
# ---------------------------------------------------------------------------
def test_r5_resource_semaphore():
    det = reglas.evaluar([_evento(event_name="xe.wait_info",
                                   wait_type="RESOURCE_SEMAPHORE", duration=200000)])
    assert "R5" in _codigos(det)


def test_r6_async_network_io():
    det = reglas.evaluar([_evento(event_name="xe.wait_info",
                                   wait_type="ASYNC_NETWORK_IO", duration=200000)])
    assert "R6" in _codigos(det)


# ---------------------------------------------------------------------------
# Corroboracion con metricas
# ---------------------------------------------------------------------------
def test_r3_corroborado_por_cpu_absoluta():
    ev = _evento(duration=1000000, cpu_time=950000)
    det = reglas.evaluar([ev], {"cpu_usr": 95.0, "cpu_sys": 10.0})
    r3 = next(d for d in det if d["regla"] == "R3")
    assert r3["corroborado"] == "confirmado"
    assert "cpu_usr" in r3["metricas"]


def test_resumen_formato():
    det = [{"regla": "R1"}, {"regla": "R3"}, {"regla": "R1"}]
    assert reglas.resumen(det) == "R1 (I/O fisico), R3 (CPU)"


# ---------------------------------------------------------------------------
# Registro ORM de la tabla de reglas
# ---------------------------------------------------------------------------
def test_alerta_regla_registrada_en_metadata():
    from app.v2 import models
    from app.v2.database import Base

    assert "alerta_regla" in {t.name for t in Base.metadata.sorted_tables}
    assert "AlertaRegla" in {c.__name__ for c in models.TABLAS}
    columnas = {c.name for c in Base.metadata.tables["dbo.alerta_regla"].columns}
    assert {"are_alt", "are_regla", "are_diagnostico"} <= columnas
