"""Servicio de SISTEMA: parametros clave/valor y resumen general del tablero.

El resumen son consultas de conteo directas sobre las tablas que se pintan en
la pantalla de inicio. Son agregaciones pequenas (un ``COUNT`` por tabla), no
consultas analiticas: para esas estan los listados con filtros y rangos.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import Date, case, func, select
from sqlalchemy.orm import Session

from app.v2.config import settings
from app.v2.models.acceso import Usuario
from app.v2.models.datos import EstadisticaCarga, Evento, Metrica
from app.v2.models.deteccion import Alerta, HeatmapAnomalia
from app.v2.models.modelo import ModeloML, PrediccionML
from app.v2.models.nodos import Instancia
from app.v2.models.sistema import Configuracion
from app.v2.services import crud

# =====================================================================
# PARAMETROS
# =====================================================================


def listar_configuracion(db: Session, pagina: int, tamano: int, orden: str):
    return crud.listar(db, Configuracion, orden or "cfg_clave", pagina=pagina, tamano=tamano)


def obtener_configuracion(db: Session, clave: str) -> Configuracion:
    return crud.obtener_o_404(db, Configuracion, "cfg_clave", clave)


def guardar_configuracion(db: Session, clave: str, valor: str, actor: int | None) -> Configuracion:
    """Crea el parametro o actualiza su valor si ya existe."""
    existente = crud.obtener(db, Configuracion, "cfg_clave", clave)
    if existente is None:
        return crud.nuevo(db, Configuracion, {"cfg_clave": clave, "cfg_valor": valor}, actor)
    return crud.cambiar(db, Configuracion, "cfg_clave", clave, {"cfg_valor": valor})


def eliminar_configuracion(db: Session, clave: str, actor: int | None) -> Configuracion:
    return crud.borrar(db, Configuracion, "cfg_clave", clave, actor=actor)


# =====================================================================
# RESUMEN
# =====================================================================


def _conteo(db: Session, modelo, **filtros) -> int:
    """``COUNT(*)`` de una tabla con igualdades exactas."""
    q = select(func.count()).select_from(modelo)
    for columna, valor in filtros.items():
        q = q.where(getattr(modelo, columna) == valor)
    return int(db.scalar(q) or 0)


# =====================================================================
# CONEXIONES
# =====================================================================


def estado_conexiones(db: Session) -> dict:
    """Estado de las tres cosas que tienen que estar vivas: la API, la base de
    v2 y el SQL Server del sistema que monitoreamos.

    Sirve para el boton "Verificar ahora" de Configuracion. No lanza
    excepcion: si algo no responde, lo dice con ``conectado: false``.
    """
    from app.v2 import database as bd

    # 1. La base de v2 (la que usa la API).
    try:
        presentes, faltantes = bd.verificar_esquema()
        base_v2 = {
            "conectado": True,
            "base": settings.nombre_base,
            "tablas_ok": len(presentes),
            "tablas_faltantes": faltantes,
            "detalle": "Conectado" if not faltantes else f"Faltan {len(faltantes)} tablas",
        }
    except Exception as exc:
        base_v2 = {"conectado": False, "detalle": f"Sin conexion: {exc.__class__.__name__}"}

    return {
        "api": {"conectado": True, "detalle": "En linea"},
        "base_v2": base_v2,
        "sistema_monitoreado": bd.sondear_monitoreo(),
        "logs": bd.sondear_logs(),
    }


def resumen(db: Session) -> dict:
    """Cifras de la pantalla de inicio."""
    ahora = datetime.now(timezone.utc).replace(tzinfo=None)
    ayer = ahora - timedelta(days=1)

    return {
        "instancias": _conteo(db, Instancia, ins_est="A"),
        "usuarios_activos": _conteo(db, Usuario, usu_est="A"),
        "modelo_activo": db.scalar(select(ModeloML.mdl_nom).where(ModeloML.mdl_est == "A")) or "sin modelo activo",
        "predicciones": _conteo(db, PrediccionML),
        "predicciones_ayer": _conteo_rango(db, PrediccionML, "prd_ini", ayer),
        "anomalias": _conteo(db, PrediccionML, prd_es_anom=True),
        "alertas": _conteo(db, Alerta, alt_est="A"),
        "alertas_criticas": _conteo(db, Alerta, alt_est="A", alt_sev="C"),
        "metricas_ayer": _conteo_rango(db, Metrica, "met_fec", ayer),
        "eventos_ayer": _conteo_rango(db, Evento, "eve_fec", ayer),
        "generado": ahora,
    }


def _conteo_rango(db: Session, modelo, columna: str, desde: datetime) -> int:
    """Filas con ``columna >= desde`` (cutoffs de "ayer")."""
    return int(db.scalar(select(func.count()).select_from(modelo).where(getattr(modelo, columna) >= desde)) or 0)


def resumen_heatmap(db: Session, dia: date) -> list[dict]:
    """Celdas del mapa de calor de un dia, listas para pintar."""
    filas = db.execute(
        select(HeatmapAnomalia.hma_hora, HeatmapAnomalia.hma_sev, HeatmapAnomalia.hma_cant)
        .where(HeatmapAnomalia.hma_fec == dia)
        .order_by(HeatmapAnomalia.hma_hora)
    ).all()
    return [{"hora": hora, "severidad": sev, "cantidad": cant} for hora, sev, cant in filas]


def resumen_disponibilidad(db: Session, dias: int = 7) -> dict:
    """Disponibilidad de los ultimos ``dias`` dias, derivado de ventanas ML.

    La v1 sacaba el uptime de la tabla ``estadisticas_carga``, que en v2 no
    escribe nadie: solo el POST manual de /datos/cargas la toca. Sin fuente
    real el widget era un 0% fijo.

    Que se puede medir de verdad es elPORCENTAJE DE VENTANAS SANAS: de cada
    ventana que el detector evaluo, cuantas no salieron anomalias
    (``prd_es_anom = 0``). Eso es "el sistema estuvo bien" en vez de "el
    servicio estuvo arriba", que es otra cosa que aqui no se mide.

    Devuelve un dia por elemento, ordenado de mas antiguo a mas reciente, y
    el promedio ponderado por ventana (no el promedio simple de dias).
    """
# prd_ini es la hora UTC de inicio de la ventana. CAST a DATE agrupa el dia.
    dias = max(1, dias)
    hoy = datetime.now(timezone.utc).date()
    primer_dia = hoy - timedelta(days=dias - 1)
    desde = datetime.combine(primer_dia, datetime.min.time())

    dia_sql = func.cast(PrediccionML.prd_ini, Date)
    filas = db.execute(
        select(
            dia_sql,
            func.count(),
            func.sum(case((PrediccionML.prd_es_anom == 1, 1), else_=0)),
        )
        .where(PrediccionML.prd_ini >= desde)
        .group_by(dia_sql)
        .order_by(dia_sql)
    ).all()

    conteos = {d: (int(total), int(anom)) for d, total, anom in filas}
    por_dia = []
    for retroceso in range(dias - 1, -1, -1):
        dia = hoy - timedelta(days=retroceso)
        ventanas, anomalas = conteos.get(dia, (0, 0))
        por_dia.append({"dia": dia, "ventanas": ventanas, "anomalas": anomalas})

    total_vent = sum(p["ventanas"] for p in por_dia)
    total_anom = sum(p["anomalas"] for p in por_dia)

    return {
        "dias": [
            {
                "dia": p["dia"].isoformat(),
                "ventanas": p["ventanas"],
                "anomalas": p["anomalas"],
                "pct": round(100.0 * (p["ventanas"] - p["anomalas"]) / p["ventanas"], 2) if p["ventanas"] else None,
            }
            for p in por_dia
        ],
        "promedio": round(100.0 * (total_vent - total_anom) / total_vent, 2) if total_vent else None,
        "ventanas": total_vent,
        "con_datos": total_vent > 0,
    }


def resumen_transacciones(db: Session, dias: int = 7) -> dict:
    """Promedio diario de transacciones por segundo, con huecos sin datos."""
    dias = max(1, dias)
    hoy = datetime.now(timezone.utc).date()
    primer_dia = hoy - timedelta(days=dias - 1)
    desde = datetime.combine(primer_dia, datetime.min.time())
    filas = db.scalars(
        select(EstadisticaCarga)
        .where(EstadisticaCarga.wks_fec >= desde)
        .order_by(EstadisticaCarga.wks_fec)
    ).all()

    por_dia = {}
    for fila in filas:
        try:
            resumen = json.loads(fila.wks_json or "{}")
            tx = resumen.get("transactions_per_sec") or {}
            count = int(tx.get("muestras") or 0)
            if count < 1:
                continue
            valor = float(tx.get("suma") or 0.0)
        except (TypeError, ValueError, AttributeError):
            continue
        dia = fila.wks_fec.date()
        actual = por_dia.setdefault(dia, {"muestras": 0, "suma": 0.0})
        actual["muestras"] += count
        actual["suma"] += valor

    resultado = []
    muestras_total = 0
    suma_total = 0.0
    for retroceso in range(dias - 1, -1, -1):
        dia = hoy - timedelta(days=retroceso)
        datos = por_dia.get(dia, {"muestras": 0, "suma": 0.0})
        count = datos["muestras"]
        suma = datos["suma"]
        muestras_total += count
        suma_total += suma
        resultado.append({
            "dia": dia.isoformat(),
            "muestras": count,
            "promedio": round(suma / count, 2) if count else None,
        })

    return {
        "dias": resultado,
        "promedio": round(suma_total / muestras_total, 2) if muestras_total else None,
        "muestras": muestras_total,
        "con_datos": muestras_total > 0,
    }