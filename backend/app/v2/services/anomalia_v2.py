"""Convierte "esta ventana es anomala" en filas de bdSteelNort.

El detector dice que una ventana se sale. Aqui eso se escribe como:

    predicciones_ml   una fila por la ventana evaluada
    metricas          las 10 muestras de la ventana      (met_prd)
    eventos           los que de verdad la explican      (eve_prd)
    logs_sql          los logs del rango                 (lgs_prd)
    alertas           la cabecera
    alerta_variable   las variables que se salieron de rango
    causas_raiz       arbol de tres niveles

De las tablas crudas no se guarda la linea de todo el dia: solo la de la
ventana anomala. Eso es lo que hace keberables las 4 tablas particionadas
(sin esto serian ~5,4 GB por ano y nodo en ``metricas`` sola).

El mapa de calor no se escribe aqui: lo mantiene el trigger
``TR_alertas_hma_rollup``, que salta solo al insertar en ``alertas``.
"""

from __future__ import annotations

import csv
import json
import logging
import math
import re
import threading
from collections import deque
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.utils import utc_now
from app.v2.database import SessionLocal
from app.v2.models.datos import EstadisticaCarga, Evento, LogSQL, Metrica
from app.v2.models.deteccion import Alerta, AlertaVariable, CausaRaiz
from app.v2.models.modelo import PrediccionML
from app.v2.models.nodos import SesionSQL
from app.v2.services.catalogo import instancia, modelo_activo

log = logging.getLogger("steelnort.v2.anomalias")

# El detector nombra las zonas con palabras; el esquema usa una letra.
ZONA_A_CODIGO = {"NORMAL": "N", "WARNING_ESCALA": "V", "CRITICA": "A"}

# logs_sql.lgs_niv es CHAR(1) y el CHECK CK_lgs_niv solo admite E, W o I.
# Elcollector manda el nivel como lo trae la fuente ("ERROR", "Warning",
# "INFORMATION", "CRITICAL"...), asi que hay que traducirlo o el INSERT
# revienta con "String or binary data would be truncated".
NIVEL_A_CODIGO = {
    "E": "E", "ERROR": "E", "ERR": "E", "CRIT": "E", "CRITICAL": "E",
    "FATAL": "E", "SEVERE": "E", "ALTA": "E",
    "W": "W", "WARN": "W", "WARNING": "W", "AVISO": "W",
    "I": "I", "INFO": "I", "INFORMATION": "I", "INFORMATIVO": "I",
    "DEBUG": "I", "TRACE": "I", "NOTICE": "I",
}

# Niveles del arbol de causa raiz (CHECK cra_nivel IN ('R','W','L')).
NIVEL_RAIZ, NIVEL_ADVERTENCIA, NIVEL_HOJA = "R", "W", "L"

# Una variable entra al diagnostico cuando se separa asi del entrenamiento.
Z_MINIMO = 1.8
Z_HOJA = 2.5

# Techos del esquema y de tamano.
MAX_VARIANTES = 15   # CK_alv_rank BETWEEN 1 AND 15
MAX_CAUSAS = 4

# Ring buffer de eventos por nodo: se van denyingindo y solo se guardan los
# que caen dentro de la ventana anomala.
BUFFER_EVENTOS = 300
BUFFER_LOGS = 300

_EVENTOS: dict[str, deque] = {}
_LOGS: dict[str, deque] = {}
_CAPTURA_LOCK = threading.Lock()
_CAPTURA_CLAVES: dict[str, set[tuple]] = {}

# Variables agrupadas por lo que significan. Solo cambia el texto del arbol.
CATEGORIAS = [
    ("API de negocio", ("api_status", "api_latency_ms")),
    ("CPU", ("cpu_usr", "cpu_sys", "cpu_wai", "load1")),
    ("Memoria", ("memory_percent", "memory_used_mb", "page_life_expectancy")),
    ("Disco y red", ("disk_read_per_sec", "disk_write_per_sec",
                     "net_send_per_sec", "net_recv_per_sec")),
    ("Sesiones y transacciones", ("active_sessions", "active_requests",
                                   "transactions_per_sec", "long_queries",
                                   "long_transactions")),
    ("Bloqueos", ("lock_waits", "total_locks", "deadlocks_per_sec")),
]

ETIQUETAS_VARIABLES = {
    "cpu_usr": "Uso de CPU de usuario",
    "cpu_sys": "Uso de CPU del sistema",
    "cpu_wai": "CPU esperando operaciones",
    "memory_percent": "Memoria utilizada",
    "memory_used_mb": "Memoria utilizada en MB",
    "page_life_expectancy": "Tiempo de vida de páginas en memoria",
    "disk_read_per_sec": "Lecturas de disco por segundo",
    "disk_write_per_sec": "Escrituras de disco por segundo",
    "net_send_per_sec": "Datos enviados por red",
    "net_recv_per_sec": "Datos recibidos por red",
    "load1": "Carga del procesador",
    "active_sessions": "Sesiones SQL activas",
    "active_requests": "Solicitudes SQL activas",
    "transactions_per_sec": "Transacciones por segundo",
    "long_queries": "Consultas de larga duración",
    "long_transactions": "Transacciones de larga duración",
    "api_latency_ms": "Tiempo de respuesta de la aplicación",
    "api_status": "Estado de la aplicación",
    "lock_waits": "Esperas por bloqueos",
    "total_locks": "Bloqueos activos",
    "deadlocks_per_sec": "Interbloqueos por segundo",
    "events_wait_count": "Errores de SQL observados",
    "batch_count": "Consultas ejecutadas",
    "batch_duration_avg_ms": "Duración media de consultas",
    "batch_duration_max_ms": "Duración máxima de consultas",
}

UNIDADES_VARIABLES = {
    "cpu_usr": "%", "cpu_sys": "%", "cpu_wai": "%",
    "memory_percent": "%", "memory_used_mb": " MB",
    "disk_read_per_sec": " bytes/s", "disk_write_per_sec": " bytes/s",
    "net_send_per_sec": " bytes/s", "net_recv_per_sec": " bytes/s",
    "transactions_per_sec": " tx/s", "api_latency_ms": " ms",
    "batch_duration_avg_ms": " ms", "batch_duration_max_ms": " ms",
}


# =====================================================================
# DIAGNOSTICO
# =====================================================================

def _variables_desviadas(pred: dict) -> list[tuple[str, float, float]]:
    """``(variable, valor, z)`` de las que se separaron del entrenamiento.

    El z sale de la media y la desviacion del ``StandardScaler`` que ya cargo
    el detector, asi que no hay que volver a tocar los artefactos.
    """
    from app.ml.detector import get_detector

    det = get_detector()
    scaler = getattr(det, "_scaler", None)
    if scaler is None or not hasattr(scaler, "mean_"):
        return []

    posiciones = getattr(det, "_posiciones", {}) or {}
    salida = []
    for nombre, valor in pred.get("features", {}).items():
        pos = posiciones.get(nombre, -1)
        if pos < 0 or pos >= len(scaler.mean_):
            continue
        escala = float(scaler.scale_[pos]) or 1.0
        z = (float(valor) - float(scaler.mean_[pos])) / escala
        if abs(z) >= Z_MINIMO:
            salida.append((nombre, float(valor), z))

    salida.sort(key=lambda t: abs(t[2]), reverse=True)
    return salida


def _severidad(det, score: float, eventos: list[dict] | None = None) -> str:
    """Una desviacion se inicia como media; solo evidencia fuerte escala la alerta."""
    for evento in eventos or []:
        if evento.get("event_name") == "xe.error_reported":
            try:
                if int(evento.get("severity") or 0) >= 20:
                    return "C"
            except (TypeError, ValueError):
                pass

    if any(evento.get("event_name") == "xe.xml_deadlock_report" for evento in eventos or []):
        return "A"

    umbrales = det.umbrales
    q01 = umbrales.get("q01", 0.0)
    brecha = max(abs(q01 - umbrales.get("q05", q01)), 0.25)
    if score < q01 - 3 * brecha:
        return "A"
    return "M"


# =====================================================================
# ESCRITURA
# =====================================================================

def _guardar_prediccion(db, modelo, nodo, pred) -> PrediccionML:
    """La fila historica. Se escribe siempre que el detector evaluo la ventana."""
    es_anomalia = bool(pred.get("es_anomalia_cruda", pred.get("es_anomalia")))
    fila = PrediccionML(
        prd_mdl=modelo.mdl_cod,
        prd_ins=nodo.ins_cod,
        prd_ini=pred["prd_ini"],
        prd_fin=pred["prd_fin"],
        prd_sco_ens=pred["score"],
        prd_umbral=pred["umbral"],
        prd_zona=ZONA_A_CODIGO.get(pred.get("zona", "NORMAL"), "N"),
        prd_es_anom=1 if es_anomalia else 0,
        prd_feats=json.dumps(pred.get("features", {})) if es_anomalia else None,
    )
    db.add(fila)
    db.flush()
    return fila


def _guardar_transacciones_diarias(db, nodo, pred) -> None:
    """Actualiza el agregado del dia con una lectura del collector."""
    fin = pred["prd_fin"]
    dia = fin.replace(hour=0, minute=0, second=0, microsecond=0)
    fila = (
        db.query(EstadisticaCarga)
        .filter(
            EstadisticaCarga.wks_ins == nodo.ins_cod,
            EstadisticaCarga.wks_fec == dia,
        )
        .first()
    )
    resumen = _leer_json(fila.wks_json) if fila else {}
    tx = resumen.get("transactions_per_sec") or {}
    valor = float((pred.get("features") or {}).get("transactions_per_sec") or 0.0)
    cantidad = int(tx.get("muestras") or 0) + 1
    suma = float(tx.get("suma") or 0.0) + valor

    resumen["transactions_per_sec"] = {
        "muestras": cantidad,
        "suma": suma,
        "promedio": suma / cantidad,
        "maximo": max(float(tx.get("maximo") or 0.0), valor),
    }
    if fila is None:
        fila = EstadisticaCarga(wks_ins=nodo.ins_cod, wks_fec=dia)
        db.add(fila)
    fila.wks_json = json.dumps(resumen)
    db.flush()


def _guardar_muestras(db, nodo, pred, pred_fila) -> None:
    """Las 10 muestras de la ventana como filas de ``metricas``.

    Solo para ventanas anomalias: es el historico que permite ver que paso
    justo antes de la alarma.
    """
    for momento, muestra in pred.get("muestras", []):
        db.add(Metrica(
            met_ins=nodo.ins_cod,
            met_prd=pred_fila.prd_cod,
            met_fec=momento,
            met_json=json.dumps(muestra),
        ))
    db.flush()


def _guardar_eventos(db, nodo, pred, pred_fila, limite: int = 20) -> None:
    """Los eventos de la ventana que explican la anomalia.

    Del buffer se toman los que caen entre ``prd_ini`` y ``prd_fin``, y se
    ordenan para quedarse con los que de verdad explican: primero los
    errores, luego los mas lentos, luego los que mas leen. El resto se
    descarta; guardar un evento por lote serian cientos de miles al dia.
    """
    inicio, fin = pred["prd_ini"], pred["prd_fin"]
    candidatos = []
    for evento in _EVENTOS.get(nodo.ins_nom, ()):
        momento = _momento(evento.get("timestamp"))
        if momento and inicio <= momento <= fin:
            candidatos.append((momento, evento))

    def gravedad(par):
        _, ev = par
        es_error = 1 if ev.get("event_name") == "xe.error_reported" else 0
        return (es_error, -float(ev.get("duration") or 0),
                -float(ev.get("logical_reads") or 0))

    for momento, ev in sorted(candidatos, key=gravedad, reverse=True)[:limite]:
        try:
            session_id = int(ev["session_id"]) if ev.get("session_id") is not None else None
        except (TypeError, ValueError):
            session_id = None
        db.add(Evento(
            eve_ins=nodo.ins_cod,
            eve_prd=pred_fila.prd_cod,
            eve_sid=session_id,
            eve_fec=momento,
            eve_dur=int(ev.get("duration") or 0),
            eve_cpu=int(ev.get("cpu_time") or 0),
            eve_lreads=int(ev.get("logical_reads") or 0),
            eve_wait=(ev.get("wait_type") or ev.get("event_name") or None),
            eve_sql=(ev.get("sql_text") or ev.get("message") or "")[:500] or None,
        ))
    db.flush()


def _guardar_sesiones(db, nodo, inicio: datetime, fin: datetime) -> None:
    """Registra el contexto de las sesiones que aparecen en XE del intervalo."""
    sesiones: dict[int, list[tuple[datetime, dict]]] = {}
    for evento in _EVENTOS.get(nodo.ins_nom, ()):
        momento = _momento(evento.get("timestamp"))
        sid = evento.get("session_id")
        if not momento or not (inicio <= momento <= fin) or sid is None:
            continue
        try:
            sid = int(sid)
        except (TypeError, ValueError):
            continue
        sesiones.setdefault(sid, []).append((momento, evento))

    for sid, actividad in sesiones.items():
        actividad.sort(key=lambda par: par[0])
        fila = (
            db.query(SesionSQL)
            .filter(
                SesionSQL.ssq_ins == nodo.ins_cod,
                SesionSQL.ssq_sid == sid,
                SesionSQL.ssq_est == "A",
            )
            .first()
        )
        acceso = next((par for par in actividad if par[1].get("event_name") == "xe.login"), actividad[0])
        salida = next((par for par in reversed(actividad) if par[1].get("event_name") == "xe.logout"), None)
        evento = acceso[1]
        if fila is None:
            fila = SesionSQL(
                ssq_ins=nodo.ins_cod,
                ssq_sid=sid,
                ssq_usr=(evento.get("username") or "")[:128] or None,
                ssq_host=(evento.get("client_hostname") or "")[:150] or None,
                ssq_prog=(evento.get("client_app_name") or "")[:100] or None,
                ssq_fec_ini=acceso[0],
                ssq_est="A",
            )
            db.add(fila)
            db.flush()
        if salida and salida[0] >= fila.ssq_fec_ini:
            fila.ssq_fec_fin = salida[0]
            fila.ssq_est = "C"
    db.flush()


def _nivel_log(valor) -> str | None:
    """Traduce el nivel del collector a la letra que admite CK_lgs_niv."""
    if valor is None:
        return None
    return NIVEL_A_CODIGO.get(str(valor).strip().upper())


def _guardar_logs(db, nodo, pred, pred_fila, logs: list[dict]) -> None:
    """Los logs que el collector haya mandado para el rango de la ventana."""
    inicio, fin = pred["prd_ini"], pred["prd_fin"]
    disponibles = list(_LOGS.get(nodo.ins_nom, ())) or (logs or [])
    for evento in _EVENTOS.get(nodo.ins_nom, ()):
        if evento.get("event_name") != "xe.error_reported":
            continue
        numero = evento.get("error_number")
        gravedad = evento.get("severity")
        try:
            nivel = "ERROR" if int(gravedad or 0) >= 11 else "WARNING"
        except (TypeError, ValueError):
            nivel = "ERROR"
        detalle = evento.get("sql_text") or evento.get("message") or "Error notificado por SQL Server"
        disponibles.append({
            "timestamp": evento.get("timestamp"),
            "nivel": nivel,
            "mensaje": f"Error SQL {numero}: {detalle}" if numero else detalle,
        })

    guardados = set()
    for log_item in disponibles:
        momento = _momento(log_item.get("timestamp") or log_item.get("fecha"))
        if not momento or not (inicio <= momento <= fin):
            continue
        clave = (momento, log_item.get("mensaje"))
        if clave in guardados:
            continue
        guardados.add(clave)
        db.add(LogSQL(
            lgs_ins=nodo.ins_cod,
            lgs_prd=pred_fila.prd_cod,
            lgs_fec=momento,
            lgs_niv=_nivel_log(log_item.get("nivel")),
            lgs_msg=log_item.get("mensaje"),
        ))
    db.flush()


def _eventos_en_ventana(nodo, pred) -> list[dict]:
    inicio, fin = pred["prd_ini"], pred["prd_fin"]
    eventos = []
    for evento in _EVENTOS.get(nodo.ins_nom, ()):
        momento = _momento(evento.get("timestamp"))
        if momento and inicio <= momento <= fin:
            eventos.append((momento, evento))
    eventos.sort(key=lambda par: (
        par[1].get("event_name") != "xe.error_reported",
        -float(par[1].get("duration") or 0),
        -float(par[1].get("logical_reads") or 0),
    ))
    return [evento for _, evento in eventos[:20]]


def _logs_en_ventana(nodo, pred, logs: list[dict] | None = None) -> list[dict]:
    inicio, fin = pred["prd_ini"], pred["prd_fin"]
    disponibles = list(_LOGS.get(nodo.ins_nom, ()))
    disponibles.extend(logs or [])
    for evento in _EVENTOS.get(nodo.ins_nom, ()):
        if evento.get("event_name") != "xe.error_reported":
            continue
        gravedad = evento.get("severity")
        try:
            nivel = "ERROR" if int(gravedad or 0) >= 11 else "WARNING"
        except (TypeError, ValueError):
            nivel = "ERROR"
        numero = evento.get("error_number")
        detalle = evento.get("sql_text") or evento.get("message") or "Error notificado por SQL Server"
        disponibles.append({
            "timestamp": evento.get("timestamp"),
            "nivel": nivel,
            "mensaje": f"Error SQL {numero}: {detalle}" if numero else detalle,
        })

    salida, vistos = [], set()
    for item in disponibles:
        momento = _momento(item.get("timestamp") or item.get("fecha"))
        clave = (momento, item.get("mensaje"))
        if momento and inicio <= momento <= fin and clave not in vistos:
            salida.append({**item, "timestamp": momento.isoformat(sep=" ")})
            vistos.add(clave)
    return salida


def _sospecha_esperada(pred: dict) -> str:
    """Describe una causa probable; no la presenta como regla confirmada."""
    causas = {nombre for nombre, _, _ in _variables_desviadas(pred)}
    if causas & {"lock_waits", "total_locks", "long_transactions", "active_requests"}:
        return "Posible contención entre transacciones o sesiones bloqueadas."
    if causas & {"total_writes", "transactions_per_sec", "long_queries"}:
        return "Posible carga elevada de escrituras o consultas concurrentes."
    if causas & {"disk_read_per_sec", "disk_write_per_sec", "net_recv_per_sec"}:
        return "Posible presión de lectura o escritura en disco o red."
    if causas & {"cpu_usr", "cpu_sys", "cpu_wai", "load1"}:
        return "Posible aumento de carga del procesador."
    if causas & {"memory_percent", "memory_used_mb", "page_life_expectancy"}:
        return "Posible presión de memoria."
    if causas & {"api_latency_ms", "api_status"}:
        return "Posible lentitud o error de respuesta de la aplicación."
    return "Cambio en el patrón de carga; revisar los indicadores observados."


def _claves_captura(ruta: Path, tipo: str) -> set[tuple]:
    clave = str(ruta)
    if clave in _CAPTURA_CLAVES:
        return _CAPTURA_CLAVES[clave]
    vistas: set[tuple] = set()
    if ruta.is_file():
        with ruta.open(encoding="utf-8-sig") as archivo:
            for linea in archivo:
                if tipo == "metricas":
                    partes = linea.split()
                    if len(partes) == 4 and partes[0] != "timestamp":
                        vistas.add((f"{partes[0]} {partes[1]}", partes[2]))
                elif tipo == "json":
                    try:
                        evento = json.loads(linea)
                        vistas.add((evento.get("timestamp"), evento.get("event_name"), evento.get("session_id")))
                    except (TypeError, ValueError):
                        continue
                else:
                    vistas.add((linea.rstrip("\n"),))
    _CAPTURA_CLAVES[clave] = vistas
    return vistas


def _archivar_anomalia(nodo_nombre: str, pred: dict, pred_cod: int, alerta_cod: int | None) -> str:
    """Añade una fila correlacionada y sus archivos al pipeline CRISP-DM."""
    mes = pred["prd_fin"].strftime("%Y%m")
    backend = Path(__file__).resolve().parents[3]
    capturas = backend / "training" / "captures" / "anomalias"
    nodo_carpeta = re.sub(r"[^A-Za-z0-9_-]+", "_", nodo_nombre).strip("_")[:40] or "nodo"
    corrida = backend / "training" / "output" / "anomalias" / f"anomalia_live_{mes}_{nodo_carpeta}"
    capturas.mkdir(parents=True, exist_ok=True)
    corrida.mkdir(parents=True, exist_ok=True)

    nodo = SimpleNamespace(ins_nom=nodo_nombre)
    eventos = _eventos_en_ventana(nodo, pred)
    logs = _logs_en_ventana(nodo, pred)
    sospecha = _sospecha_esperada(pred)
    ruta_csv = capturas / f"anomalias_{mes}.csv"
    columnas = [
        "prediccion", "alerta", "nodo", "inicio", "fin", "sospecha_esperada",
        "regla_aplicada", "metricas_json", "eventos_json", "logs_json",
    ]
    muestras = pred.get("muestras", [])
    with _CAPTURA_LOCK:
        nuevo = not ruta_csv.exists() or ruta_csv.stat().st_size == 0
        with ruta_csv.open("a", newline="", encoding="utf-8") as archivo:
            escritor = csv.DictWriter(archivo, fieldnames=columnas)
            if nuevo:
                escritor.writeheader()
            escritor.writerow({
                "prediccion": pred_cod,
                "alerta": alerta_cod or "",
                "nodo": nodo_nombre,
                "inicio": pred["prd_ini"].isoformat(sep=" "),
                "fin": pred["prd_fin"].isoformat(sep=" "),
                "sospecha_esperada": sospecha,
                "regla_aplicada": "Detección estadística sostenida (consenso de ventanas)",
                "metricas_json": json.dumps(muestras, ensure_ascii=False, default=str),
                "eventos_json": json.dumps(eventos, ensure_ascii=False, default=str),
                "logs_json": json.dumps(logs, ensure_ascii=False, default=str),
            })

        ruta_metricas = corrida / "metrics.log"
        claves_metricas = _claves_captura(ruta_metricas, "metricas")
        primera = not ruta_metricas.exists() or ruta_metricas.stat().st_size == 0
        with ruta_metricas.open("a", encoding="utf-8") as archivo:
            if primera:
                archivo.write("timestamp metric value\n")
            muestras_nuevas = muestras if primera else muestras[-1:]
            for momento, muestra in muestras_nuevas:
                fecha = _momento(momento)
                if not fecha:
                    continue
                marca = fecha.strftime("%Y-%m-%d %H:%M:%S")
                for nombre, valor in muestra.items():
                    if not isinstance(valor, (int, float)) or not math.isfinite(float(valor)):
                        continue
                    key = (marca, nombre)
                    if key not in claves_metricas:
                        archivo.write(f"{marca} {nombre} {float(valor):.8g}\n")
                        claves_metricas.add(key)

        ruta_eventos = corrida / "events.log"
        claves_eventos = _claves_captura(ruta_eventos, "json")
        with ruta_eventos.open("a", encoding="utf-8") as archivo:
            for evento in eventos:
                fila = dict(evento)
                fila["event_name"] = str(fila.get("event_name") or "").removeprefix("xe.")
                key = (fila.get("timestamp"), fila.get("event_name"), fila.get("session_id"))
                if key not in claves_eventos:
                    archivo.write(json.dumps(fila, ensure_ascii=False, default=str) + "\n")
                    claves_eventos.add(key)

        ruta_logs = corrida / "sqlserver_logs.log"
        claves_logs = _claves_captura(ruta_logs, "texto")
        with ruta_logs.open("a", encoding="utf-8") as archivo:
            for item in logs:
                fecha = _momento(item.get("timestamp"))
                if not fecha:
                    continue
                linea = f"{fecha.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]} SQL {item.get('mensaje', '')}"
                linea = linea.replace("\n", " ")
                if (linea,) not in claves_logs:
                    archivo.write(linea + "\n")
                    claves_logs.add((linea,))

        ruta_origen = corrida / "origen.json"
        if not ruta_origen.exists():
            ruta_origen.write_text(json.dumps({
                "origen": "telemetria_v2",
                "es_carga_normal": False,
                "sospecha_esperada": sospecha,
                "regla_aplicada": "Detección estadística sostenida (consenso de ventanas)",
                "csv_correlacionado": str(ruta_csv.relative_to(backend)),
            }, ensure_ascii=False, indent=2), encoding="utf-8")

    return str(ruta_csv)


def _guardar_alerta(db, nodo, pred, pred_fila, det, eventos=None) -> Alerta:
    """La cabecera. Su severidad la decide el margen bajo el umbral."""
    sev = _severidad(det, pred["score"], eventos)
    titulo = f"Cambio inusual en {nodo.ins_nom}"
    # El diagnostico arranca con la REGLA que disparo la alerta, para que se
    # lea el porque sin tener que consultar el codigo del decisor.
    fila = Alerta(
        alt_prd=pred_fila.prd_cod,
        alt_ins=nodo.ins_cod,
        alt_tipo="anomalia_ml",
        alt_sev=sev,
        alt_titulo=titulo[:200],
        alt_diag=(
            "Cambio sostenido respecto al comportamiento habitual del servidor. "
            "Consulte los indicadores, eventos y sesiones relacionados para identificar la posible causa."
        ),
        alt_est="A",
        alt_fec=pred["prd_fin"],
    )
    db.add(fila)
    db.flush()
    return fila


def _guardar_variables(db, alerta, pred) -> None:
    """Que variables explican la alerta, de la mas desviada a la menos."""
    for rango, (nombre, valor, z) in enumerate(
        _variables_desviadas(pred)[:MAX_VARIANTES], start=1
    ):
        db.add(AlertaVariable(
            alv_alt=alerta.alt_cod,
            alv_var=nombre,
            alv_valor=valor,
            alv_z=z,
            alv_rank=rango,
        ))
    db.flush()


def _guardar_causas(db, alerta, pred) -> None:
    """Arbol de tres niveles: la alerta, la categoria que la empuja, la variable.

    Raiz (``R``) -> categoria de la variable mas desviada (``W``) -> esa misma
    variable (``L``), y por cada categoria que tambien se salio.
    """
    raiz = CausaRaiz(
        cra_alt=alerta.alt_cod,
        cra_nivel=NIVEL_RAIZ,
        cra_etiq=alerta.alt_titulo,
    )
    db.add(raiz)
    db.flush()

    variables = _variables_desviadas(pred)[:MAX_CAUSAS]
    if not variables:
        return

    for categoria, nombres in CATEGORIAS:
        dentro = [(nombre, valor, z) for nombre, valor, z in variables if nombre in nombres]
        if not dentro:
            continue
        nombre, valor, z = max(dentro, key=lambda t: abs(t[2]))

        aviso = CausaRaiz(
            cra_alt=alerta.alt_cod,
            cra_padre=raiz.cra_cod,
            cra_nivel=NIVEL_ADVERTENCIA,
            cra_etiq=f"{categoria} (z={z:+.2f})",
        )
        db.add(aviso)
        db.flush()

        db.add(CausaRaiz(
            cra_alt=alerta.alt_cod,
            cra_padre=aviso.cra_cod,
            cra_nivel=NIVEL_HOJA,
            cra_etiq=f"{nombre} = {valor} (z={z:+.2f})",
        ))
        db.flush()


# =====================================================================
# ENTRADA
# =====================================================================
# ENTRADA
# =====================================================================

def _momento(valor) -> datetime | None:
    """Acepta lo que mande el collector: ISO o 'YYYY-MM-DD HH:MM:SS.mmm'."""
    if not valor:
        return None
    if isinstance(valor, datetime):
        return valor.replace(tzinfo=None)
    try:
        return datetime.fromisoformat(str(valor)).replace(tzinfo=None)
    except ValueError:
        return None


def obtener_informe(db: Session, alerta_cod: int) -> dict:
    """Devuelve el informe completo y sus filas persistidas para una alerta."""
    alerta = db.query(Alerta).filter(Alerta.alt_cod == alerta_cod).first()
    if alerta is None:
        raise HTTPException(status_code=404, detail="Alerta no encontrada")

    pred = db.query(PrediccionML).filter(PrediccionML.prd_cod == alerta.alt_prd).first()
    if pred is None:
        raise HTTPException(status_code=404, detail="La alerta no tiene prediccion")

    try:
        features = json.loads(pred.prd_feats or "{}")
    except (TypeError, ValueError):
        features = {}

    variables = [
        {
            "alv_cod": fila.alv_cod,
            "alv_var": fila.alv_var,
            "etiqueta": ETIQUETAS_VARIABLES.get(fila.alv_var, fila.alv_var.replace("_", " ")),
            "unidad": UNIDADES_VARIABLES.get(fila.alv_var, ""),
            "alv_valor": fila.alv_valor,
            "alv_z": fila.alv_z,
            "alv_rank": fila.alv_rank,
            "interpretacion": "Por encima de su nivel habitual" if (fila.alv_z or 0) > 0 else "Por debajo de su nivel habitual",
        }
        for fila in db.query(AlertaVariable).filter(AlertaVariable.alv_alt == alerta_cod).order_by(AlertaVariable.alv_rank)
    ]
    indicadores = ", ".join(v["etiqueta"].lower() for v in variables[:3])
    sospecha = _sospecha_esperada({"features": features})
    explicacion = (
        f"El sistema comparó 10 lecturas con el comportamiento habitual. "
        f"{('Se observaron desviaciones en ' + indicadores + '.') if indicadores else 'El patrón general se apartó del comportamiento habitual.'} "
        "La señal se repitió lo suficiente para abrir esta alerta."
    )

    sesiones = []
    if alerta.alt_ins is not None:
        sesiones = [
            {
                "id": fila.ssq_sid,
                "usuario": fila.ssq_usr,
                "equipo": fila.ssq_host,
                "aplicacion": fila.ssq_prog,
                "inicio": fila.ssq_fec_ini,
                "fin": fila.ssq_fec_fin,
                "estado": "Activa" if fila.ssq_est == "A" else "Cerrada",
            }
            for fila in db.query(SesionSQL)
            .filter(
                SesionSQL.ssq_ins == alerta.alt_ins,
                SesionSQL.ssq_fec_ini <= pred.prd_fin,
                or_(SesionSQL.ssq_fec_fin.is_(None), SesionSQL.ssq_fec_fin >= pred.prd_ini),
            )
            .order_by(SesionSQL.ssq_fec_ini)
        ]
    sesiones_por_id = {sesion["id"]: sesion for sesion in sesiones}

    eventos = []
    for fila in db.query(Evento).filter(Evento.eve_prd == pred.prd_cod).order_by(Evento.eve_fec):
        sesion = sesiones_por_id.get(fila.eve_sid)
        eventos.append({
            "fecha": fila.eve_fec,
            "tipo": fila.eve_wait,
            "actividad": {
                "xe.error_reported": "Error de SQL",
                "xe.xml_deadlock_report": "Interbloqueo",
                "xe.sql_batch_completed": "Consulta completada",
                "xe.rpc_completed": "Llamada a procedimiento",
            }.get(fila.eve_wait, "Actividad de SQL"),
            "duracion": fila.eve_dur,
            "cpu": fila.eve_cpu,
            "lecturas": fila.eve_lreads,
            "sql": fila.eve_sql,
            "sesion": sesion,
        })

    return {
        "alerta": {
            "codigo": alerta.alt_cod,
            "fecha": alerta.alt_fec,
            "severidad": alerta.alt_sev,
            "titulo": alerta.alt_titulo,
            "diagnostico": alerta.alt_diag,
            "estado": alerta.alt_est,
        },
        "explicacion": {
            "titulo": "Desviación del comportamiento habitual",
            "texto": explicacion,
            "sospecha": sospecha,
            "regla_aplicada": "Detección estadística sostenida: la desviación apareció en varias lecturas consecutivas.",
            "criterio": "La alerta se genera cuando la desviación se mantiene en varias lecturas, no por un cambio aislado.",
        },
        "prediccion": {
            "codigo": pred.prd_cod,
            "inicio": pred.prd_ini,
            "fin": pred.prd_fin,
            "score": pred.prd_sco_ens,
            "umbral": pred.prd_umbral,
            "zona": pred.prd_zona,
            "features": features,
        },
        "metricas": [
            {"fecha": fila.met_fec, "datos": _leer_json(fila.met_json)}
            for fila in db.query(Metrica).filter(Metrica.met_prd == pred.prd_cod).order_by(Metrica.met_fec)
        ],
        "eventos": eventos,
        "logs_sql": [
            {
                "fecha": fila.lgs_fec,
                "nivel": fila.lgs_niv,
                "nivel_texto": {"E": "Error", "W": "Aviso", "I": "Información"}.get(fila.lgs_niv, "Registro"),
                "mensaje": fila.lgs_msg,
            }
            for fila in db.query(LogSQL).filter(LogSQL.lgs_prd == pred.prd_cod).order_by(LogSQL.lgs_fec)
        ],
        "sesiones_sql": sesiones,
        "variables": variables,
        "captura_csv": f"training/captures/anomalias/anomalias_{pred.prd_fin:%Y%m}.csv",
        "causas": [
            {
                "cra_cod": fila.cra_cod,
                "cra_padre": fila.cra_padre,
                "cra_nivel": fila.cra_nivel,
                "cra_etiq": fila.cra_etiq,
            }
            for fila in db.query(CausaRaiz).filter(CausaRaiz.cra_alt == alerta_cod).order_by(CausaRaiz.cra_cod)
        ],
    }


def _leer_json(valor: str | None):
    try:
        return json.loads(valor or "{}")
    except (TypeError, ValueError):
        return {}


def _guardar_informe(db: Session, alerta_cod: int) -> Path:
    carpeta = Path(__file__).resolve().parents[3] / "logs" / "informes_diagnostico"
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f"informe_deteccion_{alerta_cod}.json"
    ruta.write_text(
        json.dumps(obtener_informe(db, alerta_cod), ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return ruta


def registrar_eventos(nodo: str, eventos: list[dict]) -> None:
    """Guarda los eventos del intervalo en el ring buffer del nodo."""
    buffer = _EVENTOS.setdefault(nodo, deque(maxlen=BUFFER_EVENTOS))
    buffer.extend(eventos or [])


def registrar_logs(nodo: str, logs: list[dict]) -> None:
    """Mantiene logs recientes para asociarlos a la ventana que disparó."""
    buffer = _LOGS.setdefault(nodo, deque(maxlen=BUFFER_LOGS))
    presentes = {
        (item.get("timestamp") or item.get("fecha"), item.get("nivel"), item.get("mensaje"))
        for item in buffer
    }
    for item in logs or []:
        clave = (item.get("timestamp") or item.get("fecha"), item.get("nivel"), item.get("mensaje"))
        if clave not in presentes:
            buffer.append(item)
            presentes.add(clave)


def persistir_anomalia(nodo_nombre: str, nodo_ip: str, pred: dict,
                       logs: list[dict] | None = None) -> dict | None:
    """Guarda cada ventana y añade detalle cuando detecta una anomalía.

    Las ventanas normales solo guardan el resultado ML; las crudas se guardan
    para ventanas anómalas y las alertas solo nacen en una activación nueva.
    """
    es_anomalia = bool(pred.get("es_anomalia_cruda", pred.get("es_anomalia")))
    alerta_nueva = bool(pred.get("alerta_nueva", pred.get("es_anomalia")))

    from app.ml.detector import get_detector

    det = get_detector() if alerta_nueva else None
    db: Session = SessionLocal()
    try:
        nodo = instancia(db, nodo_nombre, nodo_ip, pred["prd_ini"])
        modelo = modelo_activo(db)

        pred_fila = _guardar_prediccion(db, modelo, nodo, pred)
        _guardar_transacciones_diarias(db, nodo, pred)
        if es_anomalia:
            _guardar_sesiones(db, nodo, pred["prd_ini"], pred["prd_fin"])
            _guardar_muestras(db, nodo, pred, pred_fila)
            _guardar_eventos(db, nodo, pred, pred_fila)
            _guardar_logs(db, nodo, pred, pred_fila, logs or [])

        alerta = None
        if alerta_nueva:
            eventos_ventana = []
            for evento in _EVENTOS.get(nodo.ins_nom, ()):
                momento = _momento(evento.get("timestamp"))
                if momento and pred["prd_ini"] <= momento <= pred["prd_fin"]:
                    eventos_ventana.append(evento)
            alerta = _guardar_alerta(db, nodo, pred, pred_fila, det, eventos_ventana)
            _guardar_variables(db, alerta, pred)
            _guardar_causas(db, alerta, pred)

        db.commit()
        ruta_captura = None
        if es_anomalia:
            try:
                ruta_captura = _archivar_anomalia(
                    nodo_nombre, pred, pred_fila.prd_cod,
                    alerta.alt_cod if alerta else None,
                )
                from app.v2.services.reentrenamiento import revisar_umbral

                revisar_umbral()
            except Exception:
                log.exception("No se pudo archivar la ventana anómala %s", pred_fila.prd_cod)
        ruta_informe = None
        if alerta is not None:
            try:
                ruta_informe = _guardar_informe(db, alerta.alt_cod)
            except Exception:
                log.exception("No se pudo guardar el informe de la alerta %s", alerta.alt_cod)
        log.info("Ventana guardada: pred=%s nodo=%s score=%s anomalía=%s alerta=%s",
                 pred_fila.prd_cod, nodo_nombre, pred["score"], es_anomalia,
                 alerta.alt_cod if alerta else None)
        return {"nodo": nodo_nombre,
                "alerta": alerta.alt_cod if alerta else None,
                "prediccion": pred_fila.prd_cod,
                "anomalia": es_anomalia,
                "alerta_activa": bool(pred.get("alerta_activa", pred.get("es_anomalia"))),
                "severidad": alerta.alt_sev if alerta else None,
                "captura": ruta_captura,
                "informe": ruta_informe.name if ruta_informe else None}
    except Exception:
        db.rollback()
        log.exception("No se pudo guardar la anomalia de %s", nodo_nombre)
        return None
    finally:
        db.close()


def olvidar_nodo(nodo_nombre: str) -> None:
    """Saca el buffer de un nodo que dejo de empujar."""
    _EVENTOS.pop(nodo_nombre, None)
    _LOGS.pop(nodo_nombre, None)