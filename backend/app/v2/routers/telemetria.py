"""Router de telemetría V2: Ingesta en RAM, evaluación ML y persistencia de anomalías."""

from __future__ import annotations

from typing import Any, Dict
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.ml.detector import get_detector
from app.v2.services.anomalia_v2 import persistir_anomalia, registrar_eventos, registrar_logs

router = APIRouter(prefix="/telemetria", tags=["telemetria"])

# Almacén temporal en RAM para el endpoint /actual y el dashboard
MEMORIA_CACHE: Dict[str, Dict[str, Any]] = {}


class PayloadMuestra(BaseModel):
    nodo: str
    ip: str = "127.0.0.1"
    muestra: Dict[str, Any]
    # El collector ya los mandaba y Pydantic los tiraba. Ahora se quedan en un
    # ring buffer por nodo: cuando una ventana resulta anomala se guardan solo
    # los que caen dentro de ella, y son los que salen en el detalle.
    eventos: list[Dict[str, Any]] = Field(default_factory=list)
    logs: list[Dict[str, Any]] = Field(default_factory=list)


@router.post("/push")
def recibir_y_evaluar_telemetria(payload: PayloadMuestra):
    """
    Recibe la telemetría del demonio, actualiza la caché en RAM para el frontend,
    ejecuta el modelo de Machine Learning y persiste en BD si detecta anomalía.
    """
    nodo = payload.nodo
    ip = payload.ip
    muestra = payload.muestra

    # 1. Guardar en memoria RAM para lectura rápida del dashboard (/actual)
    MEMORIA_CACHE[nodo] = {
        "nodo": nodo,
        "ip": ip,
        "muestra": muestra,
        "fecha_str": muestra.get("fecha_str")
    }

   # 2. Evaluar anomalía mediante la ventana deslizante del detector
    registrar_eventos(nodo, payload.eventos)
    registrar_logs(nodo, payload.logs)
    detector = get_detector()
    resultado = detector.evaluar(nodo=nodo, muestra=muestra)

    if resultado is None:
        return {
            "estado": "acumulando",
            "mensaje": f"Ventana en proceso de llenado (< {detector.ventana} muestras).",
            "sesiones_y_transacciones": {
                "active_sessions": muestra.get("active_sessions", 0),
                "active_requests": muestra.get("active_requests", 0),
                "transactions_per_sec": muestra.get("transactions_per_sec", 0)
            }
        }

    # 3. Si se confirma la anomalía, se persiste con su causa raíz
    alerta_nueva = resultado.get("alerta_nueva", resultado.get("es_anomalia"))
    persistida = persistir_anomalia(
        nodo_nombre=nodo,
        nodo_ip=ip,
        pred=resultado,
        logs=payload.logs,
    )

    # 4. Respuesta completa con evaluación, sesiones y causas raíz
    return {
        "estado": "evaluado",
        "es_anomalia": resultado.get("es_anomalia_cruda", resultado.get("es_anomalia")),
        "alerta_activa": resultado.get("alerta_activa", resultado.get("es_anomalia")),
        "alerta_nueva": alerta_nueva,
        "score": resultado.get("score"),
        "umbral": resultado.get("umbral"),
        "zona": resultado.get("zona", "NORMAL"),
        "sesiones_y_transacciones": {
            "active_sessions": muestra.get("active_sessions", 0),
            "active_requests": muestra.get("active_requests", 0),
            "transactions_per_sec": muestra.get("transactions_per_sec", 0)
        },
        "alerta_persistida": persistida.get("alerta") if persistida else None,
        "prediccion_persistida": persistida.get("prediccion") if persistida else None,
    }

@router.get("/actual")
def obtener_actual():
    """
    Endpoint de lectura rápida que alimenta las tarjetas del Frontend 
    (CPU, Memoria, Sesiones conexioes y Transacciones) en tiempo real,
    incorporando todas las métricas transaccionales de SQL Server.
    """
    nodo_default = next(iter(MEMORIA_CACHE), "Servidor Negocio")
    data_nodo = MEMORIA_CACHE.get(nodo_default, {})
    muestra = data_nodo.get("muestra", {})

    return {
        "estado": "ok",
        "nodo": data_nodo.get("nodo", nodo_default),
        "ip": data_nodo.get("ip", "127.0.0.1"),
        "fecha_str": data_nodo.get("fecha_str"),
        "metricas": {
            # Métricas básicas del sistema
            "cpu_usr": muestra.get("cpu_usr", 0.0),
            "cpu_sys": muestra.get("cpu_sys", 0.0),
            "memory_percent": muestra.get("memory_percent", 0.0),
            "memory_used_mb": muestra.get("memory_used_mb", 0.0),
            "memory_available_mb": muestra.get("memory_available_mb", 0.0),
            "load1": muestra.get("load1", 0.0),
            "disk_read_per_sec": muestra.get("disk_read_per_sec", 0.0),
            "disk_write_per_sec": muestra.get("disk_write_per_sec", 0.0),
            "net_send_per_sec": muestra.get("net_send_per_sec", 0.0),
            "net_recv_per_sec": muestra.get("net_recv_per_sec", 0.0),

            # Métricas transaccionales de SQL Server (las que recolectas con tus queries)
            "active_sessions": muestra.get("active_sessions", 0),
            "active_requests": muestra.get("active_requests", 0),
            "long_queries": muestra.get("long_queries", 0),
            "long_transactions": muestra.get("long_transactions", 0),
            "idle_sessions": muestra.get("idle_sessions", 0),
            "lock_waits": muestra.get("lock_waits", 0),
            "total_locks": muestra.get("total_locks", 0),
            "transactions_per_sec": muestra.get("transactions_per_sec", 0),
            "batch_requests_per_sec": muestra.get("batch_requests_per_sec", 0),
            "deadlocks_per_sec": muestra.get("deadlocks_per_sec", 0),
            "events_wait_count": muestra.get("events_wait_count", 0),

            # Rendimiento de consultas. El collector publica el tiempo de
            # lote en `batch_duration_avg_ms`; `api_latency_ms` solo existe si
            # vino de la API de negocio (puerto 7070). Antes el tablero leia
            # `api_latency_ms || duration_avg_ms`, nombres que el collector
            # nunca manda, asi que la tarjeta marcaba 0 ms.
            "batch_duration_avg_ms": muestra.get("batch_duration_avg_ms", 0.0),
            "batch_duration_max_ms": muestra.get("batch_duration_max_ms", 0.0),
            "api_latency_ms": muestra.get("api_latency_ms", 0.0),
        },
    }