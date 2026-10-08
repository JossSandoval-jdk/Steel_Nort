"""Depuracion del repositorio SteelNort.

Lista los paths marcados para borrado, verifica por grep que nada vivo
los importa/referencia y solo borra con --apply.

Uso:
    python tools/limpieza.py            # dry-run (default)
    python tools/limpieza.py --apply    # borra realmente
    python tools/limpieza.py --fase 1   # solo una fase
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
RAIZ = BACKEND.parent

# Cada entrada: (fase, path relativo a la raiz del repo, motivo)
# Los paths de codigo incluyen ademas patrones que NO deben referenciarlo
# los archivos vivos (imports de python).
PLAN: list[tuple[int, str, str, list[str]]] = [
    # ---------------------------------------------------------------- Fase 1
    (1, "backend/app/main.py", "API v1: app que nadie lanza (run_backend.bat usa v2)", []),
    (1, "backend/app/database.py", "BD v1 (v2 usa app.v2.database)", []),
    (1, "backend/app/seed.py", "seed v1 (v2 usa v2/services/semilla)", []),
    (1, "backend/app/startup.py", "arranque v1", []),
    (1, "backend/app/routers", "routers v1 (v2 monta los suyos en /api/v2)", []),
    (1, "backend/app/services", "servicios v1 (v2 usa v2/services)", []),
    (1, "backend/app/models", "modelos ORM v1 (v2 usa v2/models)", []),
    (1, "backend/app/middleware", "middlewares solo usados por app.main", []),
    (1, "backend/app/schemas", "schemas v1 (v2 usa v2/schemas)", []),
    (1, "backend/app/v2/services/anomalias.py", "duplicado muerto, 0 importadores", []),
    (1, "backend/app/collector/setup_xe.sql", "huérfano: el DDL lo genera xe_collector.setup_xe", []),
    (1, "backend/training/nucleo/data_preparation/pipline.py", "huérfano, typo, invoca 05_modelado.py inexistente", []),
    (1, "backend/training/nucleo/modeling/experimental/freeze_candidato_ocsvm.py", "0 referencias", []),
    (1, "backend/run_comparacion.py", "roto: llama 03.1-03.4_deteccion_*.py inexistentes", []),
    (1, "backend/tests/test_drift.py", "cubre drift de la API v1 (v2 usa DerivaMonitor)", []),
    (1, "frontend/src/components/AnomaliasTable.jsx", "no rutado en App.jsx, consume /anomalias/diagnostico (v1)", []),
    (1, "frontend/src/pages/RolesPermisos.jsx", "no rutado en App.jsx, consume /roles (v1)", []),
    (1, "frontend/src/components/IconRefresh.jsx", "solo lo usaba AnomaliasTable", []),
    # ---------------------------------------------------------------- Fase 4
    (4, "backend/training/output/inventario", "historico v1, regenerable", []),
    (4, "backend/training/output/limpio", "historico v1, regenerable", []),
    (4, "backend/training/output/integrado", "historico v1, regenerable", []),
    (4, "backend/training/output/modelado", "historico v1, regenerable", []),
    (4, "backend/training/output/inventario_v2", "historico, historia en git", []),
    (4, "backend/training/output/limpio_v2", "historico, historia en git", []),
    (4, "backend/training/output/integrado_v2", "historico, historia en git", []),
    (4, "backend/training/output/modelado_v2", "historico, historia en git", []),
    (4, "backend/ml/backups", "backups .bak_old de artefactos", []),
    (4, "backend/training/nucleo/legacy", "carpeta vacia", []),
]

# Backups sueltos (*.bak_old, *.bak_old_<ts>, __pycache__ huérfanos)
GLOBS_FASE4 = [
    "backend/ml/artifacts/*.bak_old*",
    "backend/training/datasets/*.bak_old*",
    "backend/training/captures/spool/*.old",
]

# Referencias que impiden borrar: si aparecen en archivos vivos, fallo.
PROHIBIDO_SI_EXISTE = {
    "backend/app/routers": r"from app\.routers",
    "backend/app/services": r"from app\.services\b",
    "backend/app/models": r"from app\.models\b",
    "backend/app/middleware": r"from app\.middleware",
    "backend/app/schemas": r"from app\.schemas\b",
    "backend/app/database.py": r"from app\.database\b",
    "backend/app/seed.py": r"from app\.seed\b",
    "backend/app/startup.py": r"from app\.startup\b",
    "backend/app/main.py": r"from app\.main\b|app\.main:app",
}


IGNORAR = {".venv", "node_modules", "__pycache__", ".git", "backups", "logs"}


def _excluyendo(pattern: str, base: Path) -> list[Path]:
    """Busca patrones GLOB dentro del repo (relativos a raiz)."""
    return [p for p in RAIZ.glob(pattern) if p.exists()]


def _archivos_py() -> list[Path]:
    return [
        p
        for pat in ("backend/**/*.py", "frontend/src/**/*.js", "frontend/src/**/*.jsx", "backend/**/*.bat")
        for p in RAIZ.glob(pat)
        if not IGNORAR.intersection(p.parts) and "training/output" not in str(p)
    ]


def verificar_referencias(rel: str) -> list[str]:
    """Devuelve archivos vivos que aun referencian el path a borrar."""
    rx = PROHIBIDO_SI_EXISTE.get(rel)
    if not rx:
        return []
    pat = re.compile(rx)
    problemas = []
    for f in _archivos_py():
        if rel.replace("\\", "/") in str(f.relative_to(RAIZ)).replace("\\", "/"):
            continue  # el propio archivo a borrar
        try:
            texto = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if pat.search(texto):
            problemas.append(str(f.relative_to(RAIZ)))
    return problemas


def tamano(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="ejecuta el borrado")
    ap.add_argument("--fase", type=int, help="limita a una fase")
    args = ap.parse_args()

    items: list[tuple[int, Path, str]] = []
    for fase, rel, motivo, _ in PLAN:
        if args.fase and fase != args.fase:
            continue
        p = RAIZ / rel
        if p.exists():
            items.append((fase, p, motivo))
    for pattern in GLOBS_FASE4:
        if args.fase and args.fase != 4:
            continue
        for p in sorted(_excluyendo(pattern, RAIZ)):
            items.append((4, p, "backup/backups sueltos"))

    if not items:
        print("Nada que limpiar para ese filtro.")
        return 0

    fallas: list[str] = []
    total = 0
    print(f"{'FASE':<6}{'BYTES':>10}  PATH -> MOTIVO")
    print("-" * 100)
    for fase, p, motivo in sorted(items):
        b = tamano(p)
        total += b
        print(f"{fase:<6}{b:>10,}  {p.relative_to(RAIZ)} -> {motivo}")
        for problema in verificar_referencias(str(p.relative_to(RAIZ))):
            fallas.append(f"{p.relative_to(RAIZ)} <- {problema}")

    print("-" * 100)
    print(f"{len(items)} entradas, {total:,} bytes ({total/1024/1024:.1f} MB)")

    if fallas:
        print("\nREFERENCIAS VIVAS ENCONTRADAS (no borrar sin revisar):")
        for f in fallas:
            print("  ", f)
        return 1

    print("\nSin referencias vivas. ", end="")
    if not args.apply:
        print("Dry-run: nada se borro. Re-ejecuta con --apply para borrar.")
        return 0

    # Purga general de __pycache__ (regenerables; excluye .venv)
    if not args.fase or args.fase == 1:
        cache = [p for p in (RAIZ / "backend").rglob("__pycache__") if ".venv" not in p.parts]
        for c in cache:
            shutil.rmtree(c, ignore_errors=True)
        print(f"purgados {len(cache)} __pycache__")

    for _, p, _ in items:
        if p.exists():
            if p.is_file():
                p.unlink()
            else:
                shutil.rmtree(p, ignore_errors=True)
            print("borrado:", p.relative_to(RAIZ))
    print("Listo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
