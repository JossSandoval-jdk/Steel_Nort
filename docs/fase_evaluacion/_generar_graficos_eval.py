"""
Genera figuras extra de la fase de evaluacion (CRISP-DM 5) a partir de
artefactos ya existentes. No reentrena nada.
"""
from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT_MODELADO = ROOT / "backend" / "app" / "tools" / "output" / "modelado"
GRAF_IND = OUT_MODELADO / "indicadores" / "graficos"
GRAF_EVAL = Path(__file__).resolve().parent / "graficos"
GRAF_EVID = ROOT / "docs" / "evidencia_indicadores" / "graficos"

AZUL, GRIS, VERDE = "#2f6fb0", "#9aa7b4", "#3f9d63"
ROJO, NARANJA = "#c0504d", "#e08a2e"
ELEGIDO = "ENSEMBLE_LOF_ELL"

NORMALES = [
    "normal_alta_01",
    "normal_alta_02",
    "normal_baja_02",
    "normal_baja_03",
    "normal_larga_01",
    "normal_larga_02",
    "normal_media_03",
    "normal_media_04",
]


def estilo(ax):
    ax.grid(axis="y", color="#e3e8ee", linewidth=0.8)
    ax.set_axisbelow(True)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        ax.spines[lado].set_color("#c7cdd6")


def guardar(fig, nombre):
    GRAF_EVAL.mkdir(parents=True, exist_ok=True)
    ruta = GRAF_EVAL / nombre
    fig.tight_layout()
    fig.savefig(ruta, dpi=150, facecolor="white")
    plt.close(fig)
    print(f"  {ruta.name}")


def leer_json(rel: Path):
    with open(rel, encoding="utf-8") as fh:
        return json.load(fh)


def fig_exp1():
    ruta = OUT_MODELADO / "experimentos" / "experimento1_rendimiento_fallos.csv"
    filas = list(csv.DictReader(ruta.open(encoding="utf-8")))
    filas.sort(key=lambda r: float(r["f1"]))
    nombres = [r["esquema"] for r in filas]
    f1 = [float(r["f1"]) for r in filas]
    tpr = [float(r["tpr"]) for r in filas]
    fpr = [float(r["fpr"]) for r in filas]
    colores = [AZUL if n == ELEGIDO else GRIS for n in nombres]

    fig, axes = plt.subplots(1, 3, figsize=(13.2, 4.8))
    y = np.arange(len(nombres))
    for ax, vals, titulo, xlim in (
        (axes[0], f1, "F1 (test global q01)", 1.05),
        (axes[1], tpr, "TPR / recall", 1.05),
        (axes[2], fpr, "FPR", 0.6),
    ):
        ax.barh(y, vals, color=colores)
        ax.set_yticks(y, nombres, fontsize=8)
        ax.set_xlim(0, xlim)
        ax.set_title(titulo, fontsize=11)
        for yy, v in zip(y, vals):
            ax.text(v + 0.01, yy, f"{v:.3f}", va="center", fontsize=8)
        estilo(ax)
        ax.grid(axis="y", visible=False)
        ax.grid(axis="x", color="#e3e8ee", linewidth=0.8)
    axes[0].axvline(0.85, color=ROJO, linestyle="--", linewidth=1.1)
    fig.suptitle(
        "Experimento 1 — Rendimiento ante fallos (metrics.json, 155+353 ventanas)",
        fontsize=12,
        y=1.03,
    )
    guardar(fig, "exp1_rendimiento_fallos.png")


def fig_exp2():
    ruta = OUT_MODELADO / "experimentos" / "experimento2_tasa_falsos_positivos.csv"
    filas = [r for r in csv.DictReader(ruta.open(encoding="utf-8")) if r["esquema"] == ELEGIDO]
    umbrales = [r["umbral"] for r in filas]
    fpr = [float(r["fpr"]) * 100 for r in filas]
    f1 = [float(r["f1"]) for r in filas]
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    x = np.arange(len(umbrales))
    ax.bar(x - 0.18, fpr, 0.36, color=NARANJA, label="FPR (%)")
    ax2 = ax.twinx()
    ax2.bar(x + 0.18, f1, 0.36, color=AZUL, label="F1")
    ax.set_xticks(x, umbrales)
    ax.set_ylabel("FPR (%)")
    ax2.set_ylabel("F1")
    ax.set_title("Experimento 2 — FPR y F1 por umbral (ENSEMBLE_LOF_ELL)", fontsize=11)
    estilo(ax)
    ax.legend(loc="upper left", frameon=False)
    ax2.legend(loc="upper right", frameon=False)
    guardar(fig, "exp2_fpr_umbral.png")


def fig_exp3():
    ruta = OUT_MODELADO / "experimentos" / "experimento3_estabilidad_semillas.csv"
    filas = [r for r in csv.DictReader(ruta.open(encoding="utf-8")) if r["umbral"] == "q01"]
    filas.sort(key=lambda r: float(r["f1_mean"]))
    nombres = [r["esquema"] for r in filas]
    media = [float(r["f1_mean"]) for r in filas]
    std = [float(r["f1_std"]) for r in filas]
    colores = [AZUL if n == ELEGIDO else GRIS for n in nombres]
    fig, ax = plt.subplots(figsize=(8.8, 4.8))
    y = np.arange(len(nombres))
    ax.barh(y, media, xerr=std, color=colores, capsize=3)
    ax.set_yticks(y, nombres, fontsize=8)
    ax.set_xlabel("F1 media ± desv. (20 semillas, q01)")
    ax.set_title("Experimento 3 — Estabilidad por semillas", fontsize=12)
    ax.set_xlim(0, 1.05)
    estilo(ax)
    ax.grid(axis="y", visible=False)
    guardar(fig, "exp3_estabilidad.png")


def fig_carga_1_vs_n():
    honesto = leer_json(OUT_MODELADO / "indicadores" / "honesto.json")
    crudo = honesto["variantes"]["crudo"][ELEGIDO]["q01"]["detalle_normales"]
    norm = honesto["variantes"]["normalizado"][ELEGIDO]["q01"]["detalle_normales"]
    fpr_c = [d["alerta"] * 100 for d in crudo]
    fpr_n = [d["alerta"] * 100 for d in norm]
    etiquetas = [
        n.replace("normal_", "")
        for n in NORMALES
    ]
    x = np.arange(len(etiquetas))
    fig, ax = plt.subplots(figsize=(10.5, 4.8))
    ax.bar(x - 0.18, fpr_c, 0.36, color=ROJO, label="Sin normalizar (crudo)")
    ax.bar(x + 0.18, fpr_n, 0.36, color=VERDE, label="Normalizado por corrida")
    ax.set_xticks(x, etiquetas, rotation=25, ha="right", fontsize=8)
    ax.set_ylabel("% de ventanas alertadas (FPR)")
    ax.set_title(
        "Carga legitima (baja / media / alta) vs. falsas alarmas\n"
        "LORO, ENSEMBLE_LOF_ELL, umbral q01",
        fontsize=11,
    )
    ax.legend(frameon=False)
    estilo(ax)
    guardar(fig, "carga_fpr_por_nivel.png")


def fig_honesto_vs_global():
    fig, ax = plt.subplots(figsize=(7.4, 4.4))
    metricas = ["F1", "Recall corrida", "FPR ventana"]
    honesto = [0.9639, 1.0, 0.0274]
    global_ = [0.8136, 1.0, 0.2011]
    x = np.arange(len(metricas))
    ax.bar(x - 0.18, honesto, 0.36, color=AZUL, label="Oficial (honesto.json, LORO)")
    ax.bar(x + 0.18, global_, 0.36, color=GRIS, label="Cota conservadora (metrics.json)")
    ax.set_xticks(x, metricas)
    ax.set_ylim(0, 1.15)
    ax.set_title("Validacion del candidato ENSEMBLE_LOF_ELL", fontsize=12)
    for i, (a, b) in enumerate(zip(honesto, global_)):
        ax.text(i - 0.18, a + 0.02, f"{a:.3f}", ha="center", fontsize=8)
        ax.text(i + 0.18, b + 0.02, f"{b:.3f}", ha="center", fontsize=8)
    ax.legend(frameon=False, fontsize=8)
    estilo(ax)
    guardar(fig, "candidato_honesto_vs_global.png")


def fig_web_latencia():
    # Valores medidos ya publicados: inferencia + endpoints + pings de salud.
    ops = [
        "Inferencia\nmodelo",
        "GET /informes\n/resumen",
        "GET /alertas\n/informe",
        "GET /salud\n(30 pings)",
    ]
    ms = [0.22258, 181, 224, 2087.7]
    fig, ax = plt.subplots(figsize=(8.2, 4.6))
    barras = ax.bar(ops, ms, color=[VERDE, AZUL, AZUL, NARANJA])
    ax.axhline(3000, color=ROJO, linestyle="--", linewidth=1.2, label="meta I-4.2 / I-5.2 (3 s)")
    ax.set_ylabel("milisegundos (escala log)")
    ax.set_yscale("log")
    ax.set_title("Latencia de la web y del modelo vs. meta de 3 s", fontsize=12)
    for b, v in zip(barras, ms):
        ax.text(b.get_x() + b.get_width() / 2, v * 1.15, f"{v:.2f} ms", ha="center", fontsize=8)
    ax.legend(frameon=False)
    estilo(ax)
    guardar(fig, "web_latencia_operaciones.png")


def copiar_a_evidencia():
    GRAF_EVID.mkdir(parents=True, exist_ok=True)
    fuentes = list(GRAF_IND.glob("*.png")) + list(GRAF_EVAL.glob("*.png"))
    for src in fuentes:
        dest = GRAF_EVID / src.name
        shutil.copy2(src, dest)
    print(f"Copiados {len(fuentes)} PNG a {GRAF_EVID}")


def main():
    GRAF_EVAL.mkdir(parents=True, exist_ok=True)
    print("Graficos de evaluacion ->", GRAF_EVAL)
    fig_exp1()
    fig_exp2()
    fig_exp3()
    fig_carga_1_vs_n()
    fig_honesto_vs_global()
    fig_web_latencia()
    # Copiar tambien los de indicadores al folder de evaluacion.
    for src in GRAF_IND.glob("*.png"):
        shutil.copy2(src, GRAF_EVAL / src.name)
        print(f"  (copia) {src.name}")
    copiar_a_evidencia()
    print("Listo.")


if __name__ == "__main__":
    main()
