"""Servicio de INFORMES: resumen del periodo, anomalias y exportacion a archivo.

Todo sale de las tablas reales de la v2 (``predicciones_ml``, ``alertas``,
``alerta_variable``, ``eventos``, ``logs_sql``, ``instancias``). No hay datos de
ejemplo: si no hay filas en el rango, las listas van vacias.
"""

from __future__ import annotations

import csv
import json
import logging
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.v2.models.datos import Evento, LogSQL
from app.v2.models.deteccion import Alerta, AlertaVariable
from app.v2.models.modelo import PrediccionML
from app.v2.models.nodos import Instancia

log = logging.getLogger("steelnort.v2.informes")

# Carpeta donde el generador deja los archivos (CSV/JSON) para descargar.
DIR_EXPORTADOS = Path(__file__).resolve().parents[3] / "logs" / "informes_exportados"

# Columnas de cada dataset exportable, para que el CSV salga con cabecera
# aunque no haya ninguna fila en el rango.
COLUMNAS = {
    "alertas": ["alt_cod", "alt_fec", "alt_titulo", "alt_sev", "alt_est", "instancia", "alt_diag"],
    "anomalias": ["alv_cod", "alerta", "fecha", "variable", "valor", "z", "severidad", "estado", "instancia", "titulo"],
    "resumen": ["instancia", "ventanas", "anomalias", "alertas"],
}


def _rango(columna, desde, hasta):
    """Condiciones de fecha comunes a todas las consultas del informe."""
    condiciones = []
    if desde:
        condiciones.append(columna >= desde)
    if hasta:
        condiciones.append(columna <= hasta)
    return condiciones


# =====================================================================
# RESUMEN
# =====================================================================


def resumen(db: Session, desde=None, hasta=None) -> dict:
    """Agrega el periodo: ventanas, anomalias, alertas, eventos y logs."""
    ventanas = db.scalar(
        select(func.count()).select_from(PrediccionML).where(*_rango(PrediccionML.prd_ini, desde, hasta))
    ) or 0
    anomalias = db.scalar(
        select(func.count()).select_from(PrediccionML).where(
            PrediccionML.prd_es_anom == True, *_rango(PrediccionML.prd_ini, desde, hasta)  # noqa: E712
        )
    ) or 0
    eventos_n = db.scalar(
        select(func.count()).select_from(Evento).where(*_rango(Evento.eve_fec, desde, hasta))
    ) or 0
    logs_n = db.scalar(
        select(func.count()).select_from(LogSQL).where(*_rango(LogSQL.lgs_fec, desde, hasta))
    ) or 0

    por_severidad = {"C": 0, "A": 0, "M": 0, "B": 0}
    for sev, n in db.execute(
        select(Alerta.alt_sev, func.count())
        .where(*_rango(Alerta.alt_fec, desde, hasta))
        .group_by(Alerta.alt_sev)
    ):
        if sev in por_severidad:
            por_severidad[sev] = n
    alertas_n = sum(por_severidad.values())

    # Por nodo: ventanas y anomalias vienen de las predicciones; las alertas,
    # de su propia tabla. Se cruzan por nombre de instancia.
    por_instancia: dict[str, dict] = {}
    for nom, n, anom in db.execute(
        select(
            Instancia.ins_nom,
            func.count(PrediccionML.prd_cod),
            func.sum(case((PrediccionML.prd_es_anom == True, 1), else_=0)),  # noqa: E712
        )
        .join(PrediccionML, PrediccionML.prd_ins == Instancia.ins_cod)
        .where(*_rango(PrediccionML.prd_ini, desde, hasta))
        .group_by(Instancia.ins_nom)
    ):
        por_instancia[nom] = {"instancia": nom, "ventanas": n, "anomalias": int(anom or 0), "alertas": 0}
    for nom, n in db.execute(
        select(Instancia.ins_nom, func.count(Alerta.alt_cod))
        .join(Alerta, Alerta.alt_ins == Instancia.ins_cod)
        .where(*_rango(Alerta.alt_fec, desde, hasta))
        .group_by(Instancia.ins_nom)
    ):
        por_instancia.setdefault(nom, {"instancia": nom, "ventanas": 0, "anomalias": 0, "alertas": 0})
        por_instancia[nom]["alertas"] = n

    # Por tipo de evento. ``eve_dur`` viene en microsegundos (lo confirma el
    # filtro del collector: duration >= 500000). Se pasa a ms para mostrar.
    por_evento = []
    for tipo, n, dur, espera in db.execute(
        select(
            Evento.eve_tipo,
            func.count(),
            func.avg(Evento.eve_dur),
            func.sum(case((Evento.eve_wait.isnot(None), 1), else_=0)),
        )
        .where(*_rango(Evento.eve_fec, desde, hasta))
        .group_by(Evento.eve_tipo)
        .order_by(func.count().desc())
    ):
        por_evento.append({
            "tipo": tipo or "-",
            "ejecuciones": n,
            "dur_prom_ms": round(float(dur or 0) / 1000, 2),
            "con_espera": int(espera or 0),
        })

    return {
        "desde": desde,
        "hasta": hasta,
        "ventanas": ventanas,
        "anomalias": anomalias,
        "alertas": alertas_n,
        "por_severidad": por_severidad,
        "eventos": eventos_n,
        "logs": logs_n,
        "por_instancia": list(por_instancia.values()),
        "por_evento": por_evento,
    }


# =====================================================================
# LISTADOS
# =====================================================================


def listar_anomalias(db: Session, pagina: int, tamano: int, desde=None, hasta=None,
                     severidad=None, instancia=None) -> dict:
    """Variables fuera de rango, con severidad y nodo de su alerta."""
    q = (
        select(AlertaVariable, Alerta, Instancia.ins_nom)
        .join(Alerta, AlertaVariable.alv_alt == Alerta.alt_cod)
        .outerjoin(Instancia, Alerta.alt_ins == Instancia.ins_cod)
        .where(*_rango(Alerta.alt_fec, desde, hasta))
    )
    if severidad:
        q = q.where(Alerta.alt_sev == severidad)
    if instancia:
        q = q.where(Alerta.alt_ins == instancia)

    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    filas = db.execute(
        q.order_by(Alerta.alt_fec.desc(), AlertaVariable.alv_rank)
        .offset((pagina - 1) * tamano)
        .limit(tamano)
    ).all()
    items = [{
        "alv_cod": v.alv_cod,
        "alerta": a.alt_cod,
        "fecha": a.alt_fec,
        "variable": v.alv_var,
        "valor": float(v.alv_valor) if v.alv_valor is not None else None,
        "z": float(v.alv_z) if v.alv_z is not None else None,
        "severidad": a.alt_sev,
        "estado": a.alt_est,
        "instancia": nom,
        "titulo": a.alt_titulo,
    } for v, a, nom in filas]
    return {"total": total, "pagina": pagina, "tamano": tamano, "items": items}


def listar_alertas(db: Session, pagina: int, tamano: int, desde=None, hasta=None,
                   severidad=None, estado=None, instancia=None) -> dict:
    """Historial de alertas con el nombre del nodo."""
    q = (
        select(Alerta, Instancia.ins_nom)
        .outerjoin(Instancia, Alerta.alt_ins == Instancia.ins_cod)
        .where(*_rango(Alerta.alt_fec, desde, hasta))
    )
    if severidad:
        q = q.where(Alerta.alt_sev == severidad)
    if estado:
        q = q.where(Alerta.alt_est == estado)
    if instancia:
        q = q.where(Alerta.alt_ins == instancia)

    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    filas = db.execute(
        q.order_by(Alerta.alt_fec.desc()).offset((pagina - 1) * tamano).limit(tamano)
    ).all()
    items = [{
        "alt_cod": a.alt_cod,
        "alt_fec": a.alt_fec,
        "alt_titulo": a.alt_titulo,
        "alt_sev": a.alt_sev,
        "alt_est": a.alt_est,
        "alt_diag": a.alt_diag,
        "instancia": nom,
        "alt_fec_resu": a.alt_fec_resu,
    } for a, nom in filas]
    return {"total": total, "pagina": pagina, "tamano": tamano, "items": items}


# =====================================================================
# EXPORTACION A ARCHIVO
# =====================================================================


def generar(db: Session, tipo: str, formato: str, desde=None, hasta=None) -> dict:
    """Escribe el dataset pedido en CSV/JSON y devuelve sus metadatos."""
    tipo = (tipo or "resumen").lower()
    formato = (formato or "csv").lower()
    if tipo not in COLUMNAS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Tipo desconocido: {tipo}")
    if formato not in ("csv", "json"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Formato no soportado: {formato}")

    if tipo == "alertas":
        filas = listar_alertas(db, 1, 5000, desde, hasta)["items"]
    elif tipo == "anomalias":
        filas = listar_anomalias(db, 1, 5000, desde, hasta)["items"]
    else:  # resumen -> una fila por nodo
        filas = resumen(db, desde, hasta)["por_instancia"]

    columnas = COLUMNAS[tipo]
    DIR_EXPORTADOS.mkdir(parents=True, exist_ok=True)
    sello = datetime.now().strftime("%Y%m%d_%H%M%S")
    ruta = DIR_EXPORTADOS / f"informe_{tipo}_{sello}.{formato}"

    if formato == "json":
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(filas, f, ensure_ascii=False, indent=2, default=str)
    else:
        with open(ruta, "w", encoding="utf-8-sig", newline="") as f:
            escritor = csv.DictWriter(f, fieldnames=columnas, extrasaction="ignore")
            escritor.writeheader()
            for fila in filas:
                escritor.writerow(fila)

    est = ruta.stat()
    log.info("Informe %s exportado en %s (%d filas)", tipo, ruta.name, len(filas))
    return {
        "nombre": ruta.name,
        "bytes": est.st_size,
        "modificado": datetime.fromtimestamp(est.st_mtime),
        "tipo": tipo,
        "formato": formato,
        "filas": len(filas),
    }


def listar_exportados() -> list[dict]:
    """Archivos ya generados, del mas reciente al mas viejo."""
    if not DIR_EXPORTADOS.exists():
        return []
    salida = []
    for p in DIR_EXPORTADOS.glob("*"):
        if p.suffix.lower() in (".csv", ".json") and p.is_file():
            est = p.stat()
            salida.append({
                "nombre": p.name,
                "bytes": est.st_size,
                "modificado": datetime.fromtimestamp(est.st_mtime),
            })
    salida.sort(key=lambda a: a["modificado"], reverse=True)
    return salida


def ruta_exportado(nombre: str) -> Path:
    """Ruta de un archivo exportado, sin permitir salir de la carpeta."""
    limpio = Path(nombre).name  # descarta cualquier carpeta del nombre
    if not limpio or limpio != nombre:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nombre de archivo invalido")
    return DIR_EXPORTADOS / limpio


def eliminar_exportado(nombre: str) -> None:
    ruta = ruta_exportado(nombre)
    if not ruta.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No existe {nombre}")
    ruta.unlink()
