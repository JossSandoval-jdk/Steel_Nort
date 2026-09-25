"""Monitor periodico reutilizable (hilo daemon + estado en vivo).

Encapsula el ciclo de vida del hilo, el candado de estado y el intervalo.
Cada monitor solo aporta una funcion ``paso()`` que devuelve el dict de
estado; el hilo la ejecuta cada ``intervalo`` segundos, aislando errores.

Reutilizado por el monitor de sincronizacion (``sincronizacion.py``) y por
el monitor de deriva (``drift.py``), que antes duplicaban este codigo.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable

log = logging.getLogger("steelnort.monitor")


class MonitorPeriodico:
    """Hilo daemon que corre ``paso()`` cada ``intervalo`` segundos."""

    def __init__(self, nombre: str, intervalo: int,
                 paso: Callable[[], dict],
                 estado_inicial: dict | Callable[[], dict] | None = None) -> None:
        self.nombre = nombre
        self.intervalo = max(1, int(intervalo))
        self.paso = paso
        self.estado_inicial = estado_inicial
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._estado: dict = {}

    def _loop(self) -> None:
        log.info("Monitor '%s' iniciado (cada %ds)", self.nombre, self.intervalo)
        while not self._stop.is_set():
            try:
                self.publicar(self.paso())
            except Exception:
                log.exception("Fallo la pasada del monitor '%s'", self.nombre)
            self._stop.wait(self.intervalo)
        log.info("Monitor '%s' detenido", self.nombre)

    def start(self) -> None:
        """Arranca el hilo (idempotente)."""
        if self._thread is None or not self._thread.is_alive():
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._loop, daemon=True, name=f"{self.nombre}-monitor",
            )
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def publicar(self, estado: dict) -> dict:
        """Sobrescribe el estado en vivo (lo llama el hilo y las revisiones manuales)."""
        with self._lock:
            self._estado.clear()
            self._estado.update(estado)
            return dict(self._estado)

    def estado(self) -> dict:
        with self._lock:
            if not self._estado:
                inicial = self.estado_inicial
                if callable(inicial):
                    return inicial()
                return dict(inicial) if inicial else {}
            return dict(self._estado)