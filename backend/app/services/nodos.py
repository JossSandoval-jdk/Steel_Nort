"""Utilidades compartidas de nodos SCADA.

Concentra la logica de busqueda / auto-registro de nodos que antes
estaba duplicada en ``routers/telemetria.py``, ``services/anomalias.py``,
``services/importacion.py`` y ``services/sincronizacion.py``.

Regla SteelNort: los nodos que publican telemetria se auto-registran la
primera vez que envian una muestra. Cada llamador indica su ``origen``
para trazabilidad en ``reg_usu``.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.model_scada import NodosSCADA


def obtener_o_crear_nodo(
    db: Session,
    nombre: str,
    ip: str = "0.0.0.0",
    origen: str = "sistema",
) -> int | None:
    """Busca un nodo activo por nombre o lo auto-registra.

    Retorna el ``ndo_cod`` del nodo existente (baja logica excluida) o
    del recien creado. ``None`` si el nombre es vacio.
    """
    nombre = (nombre or "").strip()
    if not nombre:
        return None

    nodo = (
        db.query(NodosSCADA)
        .filter(NodosSCADA.ndo_nom == nombre, NodosSCADA.fec_eli.is_(None))
        .first()
    )
    if nodo is not None:
        return nodo.ndo_cod

    nodo = NodosSCADA(
        ndo_nom=nombre[:100],
        ndo_ip=ip[:45] or "0.0.0.0",
        ndo_tipo="servidor",
        ndo_est="operativo",
        reg_usu=origen[:60],
    )
    db.add(nodo)
    db.flush()
    return nodo.ndo_cod


def nodo_registrado(db: Session, nombre: str) -> bool:
    """True si el nodo ya existe en la BD (baja logica excluida)."""
    nombre = (nombre or "").strip()
    if not nombre:
        return False
    return (
        db.query(NodosSCADA)
        .filter(NodosSCADA.ndo_nom == nombre, NodosSCADA.fec_eli.is_(None))
        .first()
        is not None
    )