"""Routers de v2. Cada modulo se registra en ``main.py``."""

from app.v2.routers import acceso, auth, datos, deteccion, modelo, nodos, sistema

__all__ = ["acceso", "auth", "datos", "deteccion", "modelo", "nodos", "sistema"]