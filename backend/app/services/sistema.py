"""Servicio de metricas de la maquina.

Lee en tiempo real el estado de la CPU y la memoria RAM del sistema
donde corre el backend, usando ``psutil``. Tambien mantiene un historial
(en memoria) de las ultimas muestras para alimentar los graficos del
dashboard sin tocar la base de datos.

Principio SteelNort: NO se persiste telemetria cruda. El historial vive
en un ring buffer del proceso backend y se reinicia al reiniciar la API.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import TypedDict

import psutil

# ---------------------------------------------------------------------
# Estructuras de datos
# ---------------------------------------------------------------------


class CpuSample(TypedDict):
    """Uso de CPU en un instante (global + por nucleo)."""

    total: float
    nucleos: list[dict]


class MemSample(TypedDict):
    """Uso de memoria RAM en un instante."""

    percent: float
    used_mb: float
    total_mb: float
    available_mb: float


class SistemaSample(TypedDict):
    """Muestra completa de estado del sistema."""

    ts: str            # timestamp ISO (UTC)
    cpu: CpuSample
    mem: MemSample


# ---------------------------------------------------------------------
# Lectura de metricas puntuales
# ---------------------------------------------------------------------


def get_cpu() -> CpuSample:
    """Devuelve el uso de CPU global y por nucleo (porcentajes)."""
    # partition(): fuerza a psutil a medir durante una pequena ventana
    # para obtener un porcentaje representativo en la primera llamada.
    nucleos_percent = psutil.cpu_percent(interval=0.1, percpu=True)
    total = psutil.cpu_percent(interval=None)
    return {
        "total": round(total, 1),
        "nucleos": [
            {"id": i, "percent": round(p, 1)} for i, p in enumerate(nucleos_percent)
        ],
    }


def get_mem() -> MemSample:
    """Devuelve el uso de RAM (porcentaje y valores en MB)."""
    vm = psutil.virtual_memory()
    return {
        "percent": round(vm.percent, 1),
        "used_mb": round(vm.used / (1024**2), 1),
        "total_mb": round(vm.total / (1024**2), 1),
        "available_mb": round(vm.available / (1024**2), 1),
    }


def get_snapshot() -> SistemaSample:
    """Devuelve una muestra completa del sistema con su timestamp."""
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "cpu": get_cpu(),
        "mem": get_mem(),
    }


# ---------------------------------------------------------------------
# Historial en memoria (ring buffer con candado para hilos)
# ---------------------------------------------------------------------


class HistorialMetricas:
    """Ring buffer con las ultimas muestras del sistema.

    Almacena hasta ``capacidad`` muestras. Cuando se supera, descarta las
    mas antiguas (FIFO). Es seguro para uso concurrente con FastAPI.
    """

    def __init__(self, capacidad: int = 220) -> None:
        # ~11 min a 3 s de muestreo por endpoint; suficiente para la
        # tendencia "minuto a minuto" sin recargar memoria.
        self._capacidad = max(1, capacidad)
        self._muestras: list[SistemaSample] = []
        self._lock = threading.Lock()

    def agregar(self, muestra: SistemaSample) -> None:
        """Agrega una muestra y descarta las mas antiguas si hace falta."""
        with self._lock:
            self._muestras.append(muestra)
            if len(self._muestras) > self._capacidad:
                del self._muestras[: len(self._muestras) - self._capacidad]

    def serie(self, n: int | None = None) -> list[SistemaSample]:
        """Devuelve las ultimas ``n`` muestras (todas si ``n`` es None).

        Se devuelve una copia para evitar mutaciones entre hilos.
        """
        with self._lock:
            if n is None or n >= len(self._muestras):
                return list(self._muestras)
            return list(self._muestras[-n:])

    def ultima(self) -> SistemaSample | None:
        """Devuelve la muestra mas reciente, o None si no hay ninguna."""
        with self._lock:
            return self._muestras[-1] if self._muestras else None


# Instancia unica a nivel de aplicacion.
historial = HistorialMetricas()