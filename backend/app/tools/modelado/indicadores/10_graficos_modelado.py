"""
10_graficos_modelado.py
=======================
ADITIVO — no toca el detector ni ningun artefacto existente.

Genera los graficos de la FASE DE MODELADO a partir de los informes REALES que
ya viven en output/modelado/ (no inventa ninguna cifra). Cada figura cita el
indicador que soporta, con su codigo y nombre como estan en docs/Indicadores_v2.md:

    I-1.2  Indice de calidad de datos
    I-2.1  F1-Score de deteccion
    I-2.2  Variables con correlacion relevante
    I-3.1  Precision de clasificacion por tipo
    I-3.2  Coincidencia de severidad
    I-3.3  Efectividad del diagnostico
    I-4.2  Tiempo de respuesta de dashboard y alertas
    I-5.1  Recall de deteccion
    I-5.2  Tiempo de respuesta de operaciones principales
    I-5.3  Tasa de funcionamiento (pruebas)
    I-5.4  Disponibilidad en horario del OLTP
    I-0    Reduccion del tiempo de deteccion (TTFA como insumo)

Fuentes:
    indicadores/honesto.json                  ranking de esquemas (I-2.1, I-5.1)
    validacion/seeds.json                     estabilidad por semilla (I-2.1, I-5.1)
    validacion/metrics.json                   test global (I-5.1; legacy para F1)
    modelado/correlacion.json                 pares con |r| >= 0.6 (I-2.2)
    validacion/calidad.json                   auditoria de variables (I-1.2)
    validacion/robustez.json + latencia.json  robustez y costo (I-4.2, I-5.2)
    indicadores/diagnostico_final.json        deteccion, TTFA, severidad (I-3.2, I-3.3)
    indicadores/clasificador_tipo.json        top-1/2/3 y confusion LORO (I-3.1)
    indicadores/clasificador_tipo_cuando.json acierto segun el momento (I-3.1)
    indicadores/tiempos_operacion.json        latencia por operacion (I-5.2; si existe)
    indicadores/tasa_pruebas.json             suite pytest (I-5.3)
    indicadores/disponibilidad.json           pings a /salud (I-5.4; latencia en I-5.2)

Salida: output/modelado/indicadores/graficos/*.png

Nota: requiere matplotlib (ya presente en backend/.venv; NO esta declarado en
backend/requirements.txt). El backend en produccion no lo usa: solo este script
de analisis.

Uso:
    python indicadores/10_graficos_modelado.py
"""

import json
import os
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")                              # sin ventana: solo archivos
import matplotlib.pyplot as plt                    # noqa: E402

_AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(_AQUI.parent))
from modelado_config import DIR_MODELADO, log      # noqa: E402

DIR_VAL = os.path.join(DIR_MODELADO, "indicadores")     # informes de esta capa
DIR_LEGACY = os.path.join(DIR_MODELADO, "validacion")   # informes del harness 03
DIR_GRAF = os.path.join(DIR_VAL, "graficos")

# Paleta sobria (misma en todas las figuras).
AZUL, GRIS, VERDE = "#2f6fb0", "#9aa7b4", "#3f9d63"
ROJO, NARANJA = "#c0504d", "#e08a2e"
ELEGIDO = "ENSEMBLE_LOF_ELL"                       # modelo en produccion

# Etiqueta legible por tipo de fallo (misma que 08_entrenar_clasificador_tipo).
ETIQUETAS_TIPO = {
    "fault1": "Escrituras al log por INSERTs concurrentes",
    "fault2": "Full scan por falta de indice",
    "fault3": "Carga pesada sobre la API",
    "fault5": "Commits concurrentes",
    "lockwait": "Retencion de lock entre sesiones",
    "normal": "Comportamiento normal",
}


# ==========================================
# Utilidades
# ==========================================
def leer(nombre):
    """Carga un informe JSON: primero en indicadores/, si no en validacion/."""
    for base in (DIR_VAL, DIR_LEGACY):
        ruta = os.path.join(base, nombre)
        if os.path.isfile(ruta):
            with open(ruta, encoding="utf-8") as fh:
                return json.load(fh)
    raise FileNotFoundError(nombre)


def guardar(fig, nombre):
    """Guarda la figura como PNG y la cierra."""
    ruta = os.path.join(DIR_GRAF, nombre)
    fig.tight_layout()
    fig.savefig(ruta, dpi=150, facecolor="white")
    plt.close(fig)
    log(f"  {nombre}")


def _estilo(ax):
    """Estilo comun de ejes: grilla suave, sin marcos innecesarios."""
    ax.grid(axis="y", color="#e3e8ee", linewidth=0.8)
    ax.set_axisbelow(True)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        ax.spines[lado].set_color("#c7cdd6")


# ==========================================
# I-2.1  F1-Score de deteccion
# ==========================================
def fig_ranking(datos):
    """F1 normalizado q01 por esquema + punto de operacion por ventana."""
    ranking = sorted(datos["ranking_f1_normalizado_q01"],
                     key=lambda r: r["f1"])
    nombres = [r["esquema"] for r in ranking]
    f1 = [r["f1"] for r in ranking]
    colores = [AZUL if n == ELEGIDO else GRIS for n in nombres]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.5, 5.4))

    y = np.arange(len(nombres))
    ax1.barh(y, f1, color=colores)
    ax1.set_yticks(y, nombres, fontsize=9)
    ax1.set_xlim(0, 1.05)
    ax1.set_xlabel("F1 (normalizado, umbral q01)")
    ax1.set_title("Ranking de esquemas por F1\n(dejar-una-corrida-fuera)",
                  fontsize=11)
    ax1.axvline(0.85, color=ROJO, linestyle="--", linewidth=1.2)
    ax1.text(0.855, len(nombres) - 0.4, "meta 85 %", color=ROJO, fontsize=8)
    for yy, valor in zip(y, f1):
        ax1.text(valor + 0.01, yy, f"{valor:.4f}", va="center", fontsize=8)
    _estilo(ax1)
    ax1.grid(axis="y", visible=False)
    ax1.grid(axis="x", color="#e3e8ee", linewidth=0.8)

    # Punto de operacion por ventana (TPR vs FPR): cada esquema es un punto.
    v = datos["variantes"]["normalizado"]
    orden = sorted(v, key=lambda k: v[k]["q01"]["fpr_ventana"])
    xs = [v[k]["q01"]["fpr_ventana"] for k in orden]
    ys = [v[k]["q01"]["tpr_ventana"] for k in orden]
    ax2.plot([0, 1], [0, 1], color="#d0d5dc", linewidth=0.8, zorder=1)
    for k, xx, yy in zip(orden, xs, ys):
        resaltado = k == ELEGIDO
        ax2.scatter([xx], [yy], s=90 if resaltado else 46,
                    color=AZUL if resaltado else GRIS, zorder=3)
        ax2.annotate(k, (xx, yy), textcoords="offset points", xytext=(6, 5),
                     fontsize=7.5, color=AZUL if resaltado else "#44505e")
    ax2.set_xlabel("FPR por ventana (falsas alarmas)")
    ax2.set_ylabel("TPR por ventana (recall, I-5.1)")
    ax2.set_xlim(-0.02, 0.42)
    ax2.set_ylim(0, 1.05)
    ax2.set_title("Punto de operacion por ventana\n(umbral q01)", fontsize=11)
    _estilo(ax2)
    ax2.grid(color="#e3e8ee", linewidth=0.8)

    fig.suptitle("I-2.1  F1-Score de deteccion por esquema", fontsize=13, y=1.02)
    guardar(fig, "I-2.1_ranking_esquemas.png")


# ==========================================
# I-2.1  Estabilidad por semilla
# ==========================================
def fig_seeds(datos):
    """F1 medio +/- desviacion por esquema y umbral (varias semillas)."""
    umbrales = ["q01", "q05", "q10"]
    esquemas = sorted({r["esquema"] for r in datos["resumen"]})
    pos = np.arange(len(esquemas))
    ancho = 0.26
    tonos = {"q01": AZUL, "q05": NARANJA, "q10": ROJO}

    fig, ax = plt.subplots(figsize=(11, 5.2))
    for i, u in enumerate(umbrales):
        medias, desvs = [], []
        for e in esquemas:
            fila = next((r for r in datos["resumen"]
                         if r["esquema"] == e and r["umbral"] == u), None)
            medias.append(fila["f1_mean"] if fila else 0.0)
            desvs.append(fila["f1_std"] if fila else 0.0)
        ax.bar(pos + (i - 1) * ancho, medias, ancho, yerr=desvs, capsize=3,
               color=tonos[u], label=f"umbral {u}")

    ax.set_xticks(pos, esquemas, fontsize=9)
    ax.set_ylabel(f"F1 medio (+/- desv.) sobre {datos['n_seeds']} semillas")
    ax.set_ylim(0, 1.05)
    ax.set_title("I-2.1  Estabilidad del F1-Score de deteccion frente a la semilla",
                 fontsize=12)
    ax.legend(frameon=False, fontsize=9)
    _estilo(ax)
    guardar(fig, "I-2.1_estabilidad_semillas.png")


# ==========================================
# I-2.2  Variables con correlacion relevante
# ==========================================
def fig_correlacion(datos):
    """Pares de variables con |r| >= 0.6 (los 15 de mayor |r|)."""
    pares = sorted(datos["pares"], key=lambda p: -abs(p["pearson"]))
    top = pares[:15][::-1]
    etiquetas = [f"{p['var_a']}  \u2194  {p['var_b']}" for p in top]
    valores = [p["pearson"] for p in top]
    colores = [AZUL if x >= 0 else NARANJA for x in valores]

    fig, ax = plt.subplots(figsize=(11, 6))
    y = np.arange(len(top))
    ax.barh(y, valores, color=colores)
    ax.set_yticks(y, etiquetas, fontsize=8)
    ax.axvline(0.6, color=ROJO, linestyle="--", linewidth=1.0)
    ax.axvline(-0.6, color=ROJO, linestyle="--", linewidth=1.0)
    ax.set_xlim(-1.05, 1.05)
    ax.set_xlabel("Correlacion de Pearson (r)")
    ax.set_title(f"I-2.2  Variables con correlacion relevante (|r| \u2265 0.6)\n"
                 f"{len(pares)} pares en el dataset; se muestran los 15 de mayor |r|",
                 fontsize=12)
    _estilo(ax)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color="#e3e8ee", linewidth=0.8)
    guardar(fig, "I-2.2_correlacion.png")


# ==========================================
# I-3.1  Precision de clasificacion por tipo
# ==========================================
def fig_confusion(datos):
    """Matriz de confusion LORO de la configuracion desplegada."""
    nombre = datos["elegida"]
    matriz = datos["metricas_loro"][nombre]["matriz_confusion"]
    reales = sorted(matriz)
    predichos = sorted({p for fila in matriz.values() for p in fila})
    grilla = np.array([[matriz[r].get(p, 0) for p in predichos] for r in reales])

    fig, ax = plt.subplots(figsize=(8.2, 6.2))
    im = ax.imshow(grilla, cmap="Blues")
    ax.set_xticks(np.arange(len(predichos)), predichos, rotation=45, ha="right")
    ax.set_yticks(np.arange(len(reales)), reales)
    ax.set_xlabel("Tipo predicho")
    ax.set_ylabel("Tipo real")
    ax.set_title(f"I-3.1  Precision de clasificacion por tipo (LORO, {nombre})\n"
                 f"top-1 = {datos['metricas_loro'][nombre]['top1']:.1%}  ·  "
                 f"top-2 = {datos['metricas_loro'][nombre]['top2']:.1%}", fontsize=11)
    umbral = grilla.max() / 2 if grilla.max() else 0.5
    for i in range(len(reales)):
        for j in range(len(predichos)):
            if grilla[i, j]:
                ax.text(j, i, int(grilla[i, j]), ha="center", va="center",
                        fontsize=9, color="white" if grilla[i, j] > umbral else "#20303f")
    fig.colorbar(im, ax=ax, shrink=0.8, label="ventanas")
    leyenda = "  |  ".join(f"{k}: {v}" for k, v in ETIQUETAS_TIPO.items())
    fig.text(0.5, -0.02, leyenda, ha="center", fontsize=7, color="#55606e")
    guardar(fig, "I-3.1_matriz_confusion.png")


def fig_topk_clasificador(datos):
    """Top-1/2/3 de las dos variantes de entrenamiento."""
    variantes = ["con_normal", "solo_tipos"]
    metricas = ["top1", "top2", "top3"]
    pos = np.arange(len(metricas))
    ancho = 0.38

    fig, ax = plt.subplots(figsize=(9, 5))
    for i, v in enumerate(variantes):
        vals = [datos["metricas_loro"][v][m] for m in metricas]
        barras = ax.bar(pos + (i - 0.5) * ancho, vals, ancho,
                        color=AZUL if v == datos["elegida"] else GRIS, label=v)
        ax.bar_label(barras, fmt="%.1f%%", fontsize=8,
                     labels=[f"{x * 100:.1f}%" for x in vals], padding=2)
    ax.set_xticks(pos, ["top-1", "top-2", "top-3"])
    ax.set_ylim(0, 1.08)
    ax.set_ylabel("Acierto (LORO, por ventana)")
    ax.set_title("I-3.1  Precision de clasificacion por tipo — acierto top-1/2/3\n"
                 f"(config elegida: {datos['elegida']}, "
                 f"{datos['ventanas_fallo']} ventanas de fallo)", fontsize=11)
    ax.legend(frameon=False, fontsize=9)
    _estilo(ax)
    guardar(fig, "I-3.1_topk_tipo.png")


def fig_cuando(datos):
    """Top-1/2/3 segun el momento en que se evalue el fallo."""
    var = datos["resumen"]["variantes"]
    momentos = ["primera", "pico", "evento"]
    metricas = ["top1", "top2", "top3"]
    pos = np.arange(len(momentos))
    ancho = 0.26
    tonos = [GRIS, NARANJA, AZUL]

    fig, ax = plt.subplots(figsize=(9.5, 5.2))
    for i, m in enumerate(metricas):
        vals = [var[v][m] for v in momentos]
        ax.bar(pos + (i - 1) * ancho, vals, ancho, color="none",
               edgecolor=tonos[i], linewidth=1.8, label=m)
        for x, valor in zip(pos + (i - 1) * ancho, vals):
            ax.text(x, valor + 0.012, f"{valor * 100:.0f}%", ha="center",
                    fontsize=8, color=tonos[i])
    ax.set_xticks(pos, ["primera ventana\n(lo que emite la alerta hoy)",
                        "ventana pico", "evento completo\n(promedio)"], fontsize=9)
    ax.set_ylim(0, 1.08)
    ax.set_ylabel(f"Acierto sobre {datos['resumen']['faults']} fallos")
    ax.set_title("I-3.1  Precision de clasificacion por tipo segun CUANDO se "
                 "clasifique", fontsize=12)
    ax.legend(frameon=False, fontsize=9)
    _estilo(ax)
    guardar(fig, "I-3.1_cuando_clasificar.png")


# ==========================================
# I-3.2  Coincidencia de severidad
# ==========================================
def fig_severidad(datos):
    """Tasa de deteccion y distribucion de severidad emitida."""
    r = datos["resumen"]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.6))

    detectados, no_det = r["detectados_modelo"], r["faults"] - r["detectados_modelo"]
    ax1.barh([0], [detectados], color=VERDE)
    ax1.barh([0], [no_det], left=[detectados], color=ROJO)
    ax1.set_xlim(0, r["faults"])
    ax1.set_yticks([])
    ax1.set_xlabel("fallos del conjunto de validacion")
    ax1.set_title(f"Deteccion: {detectados}/{r['faults']} fallos "
                  f"({r['tasa_deteccion']:.0%})", fontsize=11)
    ax1.text(detectados / 2, 0, f"detectados {detectados}", ha="center",
             va="center", color="white", fontsize=10)
    ax1.text(detectados + no_det / 2, 0, f"{no_det}", ha="center", va="center",
             color="white", fontsize=10)
    _estilo(ax1)
    ax1.grid(visible=False)

    sev = r["distribucion_severidad"]
    claves = sorted(sev)
    barras = ax2.bar(claves, [sev[k] for k in claves],
                     color=[ROJO, NARANJA][:len(claves)])
    ax2.bar_label(barras, fontsize=9, padding=2)
    ax2.set_ylabel("fallos")
    ax2.set_title("Severidad emitida\n(sin ground truth: solo distribucion)",
                  fontsize=11)
    _estilo(ax2)

    fig.suptitle("I-3.2  Coincidencia de severidad — severidad emitida y deteccion",
                 fontsize=13, y=1.03)
    guardar(fig, "I-3.2_severidad_deteccion.png")


# ==========================================
# I-3.3  Efectividad del diagnostico
# ==========================================
def fig_efectividad(datos):
    """Coincidencia de las variables detectadas con la huella esperada."""
    r = datos["resumen"]
    con, sin = r["con_coincidencia_huella"], r["detectados_modelo"] - r["con_coincidencia_huella"]
    total = r["detectados_modelo"]
    meta = 0.85 * total

    fig, ax = plt.subplots(figsize=(8, 5))
    barras = ax.bar(["con coincidencia\nde huella", "sin coincidencia"],
                    [con, sin], color=[VERDE, ROJO])
    ax.bar_label(barras, fontsize=10, padding=2)
    ax.axhline(meta, color=AZUL, linestyle="--", linewidth=1.4,
               label=f"meta 85 % ({meta:.1f}/{total})")
    ax.set_ylabel("fallos detectados")
    ax.set_ylim(0, total * 1.15)
    ax.set_title("I-3.3  Efectividad del diagnostico\n"
                 f"variables detectadas vs. huella esperada: "
                 f"{r['efectividad_diagnostico']:.1%} ({con}/{total})", fontsize=11)
    ax.legend(frameon=False, fontsize=9)
    _estilo(ax)
    guardar(fig, "I-3.3_efectividad_diagnostico.png")


# ==========================================
# I-4.2  Tiempo de respuesta (costo) + robustez
# ==========================================
def fig_robustez(robustez, latencia):
    """Robustez a ruido/escala y costo de inferencia."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.6))

    etiquetas = ["ruido z=0.005", "escala x5"]
    tasas = [robustez["resultados"]["ruido_z005"]["tasa"],
             robustez["resultados"]["escala_x5"]["tasa"]]
    barras = ax1.bar(etiquetas, [t * 100 for t in tasas], color=[NARANJA, VERDE])
    ax1.bar_label(barras, labels=[f"{t * 100:.2f}%" for t in tasas],
                  fontsize=9, padding=2)
    ax1.set_ylabel("ventanas que cambian de decision (%)")
    ax1.set_title("Robustez de la alerta (apoyo a I-2.1)\n(umbral q01)",
                  fontsize=11)
    _estilo(ax1)

    ax2.bar(["inferencia\npor ventana"], [latencia["us_por_ventana"]], color=AZUL)
    ax2.set_ylabel("microsegundos")
    ax2.set_title(f"Costo de inferencia (I-4.2)\n({latencia['n']} ventanas, "
                  f"{latencia['seg_total'] * 1000:.0f} ms total)", fontsize=11)
    ax2.text(0, latencia["us_por_ventana"], f"{latencia['us_por_ventana']:.0f} us",
             ha="center", va="bottom", fontsize=10)
    _estilo(ax2)

    fig.suptitle("I-4.2  Tiempo de respuesta: costo de inferencia y robustez",
                 fontsize=13, y=1.03)
    guardar(fig, "I-4.2_costo_inferencia_robustez.png")


# ==========================================
# I-0  Reduccion del tiempo de deteccion (TTFA)
# ==========================================
def fig_ttfa(datos):
    """Tiempo hasta la primera alerta, por fallo detectado."""
    fallos = [p for p in datos["por_fault"] if p["ttfa_seg"] is not None]
    fallos.sort(key=lambda p: p["ttfa_seg"])
    etiquetas = [f"{p['run']} · {p['fault']}" for p in fallos]
    ttfa = [p["ttfa_seg"] for p in fallos]
    mediana = float(np.median(ttfa))

    fig, ax = plt.subplots(figsize=(13, 5.2))
    pos = np.arange(len(fallos))
    ax.bar(pos, ttfa, color=AZUL)
    ax.axhline(mediana, color=ROJO, linestyle="--", linewidth=1.4,
               label=f"mediana {mediana:.1f} s")
    ax.set_xticks(pos, etiquetas, rotation=90, fontsize=7.5)
    ax.set_ylabel("TTFA (segundos)")
    ax.set_title(f"I-0  Tiempo hasta la primera alerta (insumo del tiempo de "
                 f"deteccion)\n{len(fallos)} fallos detectados · "
                 f"media {datos['resumen']['ttfa_medio_seg']:.1f} s · "
                 f"mediana {mediana:.1f} s", fontsize=11)
    ax.legend(frameon=False, fontsize=9)
    _estilo(ax)
    guardar(fig, "I-0_ttfa.png")


# ==========================================
# I-1.2  Indice de calidad de datos
# ==========================================
def fig_calidad(calidad):
    """Variables del modelo, constantes y variables mas dispersas (ceros)."""
    pv = calidad["por_variable"]
    total = len(pv)
    en_modelo = sum(1 for x in pv if x["en_modelo"])
    constantes = sum(1 for x in pv if x["constante"])

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.5, 5.4))

    barras = ax1.bar(["candidatas", "en el modelo", "constantes"],
                     [total, en_modelo, constantes], color=[GRIS, AZUL, ROJO])
    ax1.bar_label(barras, fontsize=9, padding=2)
    ax1.set_ylabel("variables")
    ax1.set_title("Auditoria de variables\n(fuera de la linea base sana)",
                  fontsize=11)
    _estilo(ax1)

    top = sorted(pv, key=lambda x: -x["pct_ceros"])[:12]
    top.reverse()
    pos = np.arange(len(top))
    ax2.barh(pos, [x["pct_ceros"] for x in top], color=GRIS)
    ax2.set_yticks(pos, [x["variable"] for x in top], fontsize=8)
    ax2.set_xlabel("% de muestras en cero")
    ax2.set_title("Variables mas dispersas (fondo en cero)", fontsize=11)
    _estilo(ax2)
    ax2.grid(axis="y", visible=False)
    ax2.grid(axis="x", color="#e3e8ee", linewidth=0.8)

    fig.suptitle(
        f"I-1.2  Indice de calidad de datos — completitud "
        f"({calidad['ventanas_modelo']['train_nan']} NaN / "
        f"{calidad['ventanas_modelo']['train_inf']} inf en entrenamiento)",
        fontsize=13, y=1.02)
    guardar(fig, "I-1.2_calidad_datos.png")


# ==========================================
# I-5.1  Recall de deteccion
# ==========================================
def fig_recall(honesto, seeds, metrics):
    """Recall por protocolo de evaluacion y estabilidad por umbral (meta 85 %)."""
    q = honesto["variantes"]["normalizado"][ELEGIDO]["q01"]
    fila_global = next(m for m in metrics["metricas"]
                       if m["esquema"] == ELEGIDO and m["umbral"] == "q01")
    seed_q01 = next(r for r in seeds["resumen"]
                    if r["esquema"] == ELEGIDO and r["umbral"] == "q01")

    protocolos = ["Honesto\npor corrida", "Honesto\npor ventana",
                  "Test global\npor ventana", "20 semillas\n(media q01)"]
    valores = [q["tpr_corrida"], q["tpr_ventana"],
               fila_global["tpr"], seed_q01["tpr_mean"]]
    detalles = ["13/13", f"{q['tpr_ventana']:.4f}", "155/155",
                f"{seed_q01['tpr_mean']:.4f}\n\u00b1 {seed_q01['tpr_std']:.4f}"]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.6, 5.0))

    pos = np.arange(len(protocolos))
    barras = ax1.bar(pos, [v * 100 for v in valores], 0.6,
                     color=[VERDE, GRIS, AZUL, NARANJA])
    ax1.bar_label(barras, labels=[d for d in detalles], fontsize=8, padding=3)
    ax1.axhline(85, color=ROJO, linestyle="--", linewidth=1.4,
                label="meta I-5.1 (\u2265 85 %)")
    ax1.set_xticks(pos, protocolos, fontsize=9)
    ax1.set_ylim(0, 114)
    ax1.set_ylabel("Recall / TPR (%)")
    ax1.set_title("Recall por protocolo de evaluacion\n"
                  f"({ELEGIDO}, umbral q01)", fontsize=11)
    ax1.legend(frameon=False, fontsize=9, loc="lower right")
    _estilo(ax1)

    # Estabilidad del recall frente al umbral (20 semillas).
    umbrales = ["q01", "q05", "q10"]
    medias, desvs = [], []
    for u in umbrales:
        fila = next(r for r in seeds["resumen"]
                    if r["esquema"] == ELEGIDO and r["umbral"] == u)
        medias.append(fila["tpr_mean"])
        desvs.append(fila["tpr_std"])
    x = np.arange(len(umbrales))
    barras2 = ax2.bar(x, [m * 100 for m in medias], 0.55,
                      yerr=[d * 100 for d in desvs], capsize=4,
                      color=[AZUL, VERDE, GRIS])
    ax2.bar_label(barras2, labels=[f"{m:.4f}" for m in medias],
                  fontsize=8, padding=3)
    ax2.axhline(85, color=ROJO, linestyle="--", linewidth=1.4)
    ax2.set_xticks(x, umbrales)
    ax2.set_ylim(0, 114)
    ax2.set_xlabel(f"umbral (media sobre {seeds['n_seeds']} semillas)")
    ax2.set_ylabel("Recall / TPR (%)")
    ax2.set_title("Estabilidad del recall frente a la semilla", fontsize=11)
    _estilo(ax2)

    fig.suptitle("I-5.1  Recall de deteccion \u2014 meta \u2265 85 %",
                 fontsize=13, y=1.02)
    guardar(fig, "I-5.1_recall_deteccion.png")


# ==========================================
# I-5.2  Tiempo de respuesta de operaciones principales
# ==========================================
def fig_tiempos_operacion(latencia, disp, tiempos=None):
    """Latencia de las operaciones principales vs. la meta de 3 s.

    Si existe ``indicadores/tiempos_operacion.json`` (lo genera
    ``12_tiempos_operacion.py``) se usan sus medias por operacion; si no, se
    cae a los valores ya registrados en los artefactos (inferencia del modelo
    y ping de salud) y a las cifras de endpoints documentadas.
    """
    if tiempos and tiempos.get("operaciones"):
        pares = [(op.replace("_", " ").title(), est["media_ms"])
                 for op, est in tiempos["operaciones"].items()
                 if est.get("media_ms") is not None]
        fuente = "medicion por operacion (12_tiempos_operacion.py)"
    else:
        salud = disp.get("latencia_media_ms")
        pares = [
            ("Inferencia\ndel modelo", latencia["us_por_ventana"] / 1000.0),
            ("GET /informes/\nresumen", 181.0),
            ("GET /alertas/\n{id}/informe", 224.0),
            ("GET /salud\n(ping de BD)", salud),
        ]
        fuente = ("latencia.json + disponibilidad.json + endpoints documentados "
                  "(sin tiempos_operacion.json)")

    pares = [p for p in pares if p[1] is not None]
    nombres = [p[0] for p in pares]
    valores = [p[1] for p in pares]

    fig, ax = plt.subplots(figsize=(9.2, 5.0))
    pos = np.arange(len(nombres))
    # Verde: sub-milisegundo (inferencia). Naranja: el mas lento medido.
    colores = [NARANJA if v == max(valores) else AZUL for v in valores]
    barras = ax.barh(pos, valores, color=colores)
    ax.axvline(3000, color=ROJO, linestyle="--", linewidth=1.4,
               label="meta I-5.2 (\u2264 3 s)")
    ax.set_yticks(pos, nombres, fontsize=9)
    ax.set_xscale("log")
    ax.set_xlim(0.1, 8000)
    ax.set_xlabel("milisegundos (escala log)")
    ax.set_title(f"I-5.2  Tiempo de respuesta de las operaciones principales\n"
                 f"peor caso medido {max(valores):.0f} ms \u2264 3 s", fontsize=12)
    for b, v in zip(barras, valores):
        ax.text(v * 1.15, b.get_y() + b.get_height() / 2, f"{v:.2f} ms",
                va="center", fontsize=8)
    ax.legend(frameon=False, fontsize=9, loc="lower right")
    _estilo(ax)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color="#e3e8ee", linewidth=0.8)
    fig.text(0.5, -0.04, f"Fuente: {fuente}", ha="center", fontsize=7,
             color="#55606e")
    guardar(fig, "I-5.2_tiempos_operacion.png")


# ==========================================
# I-5.3  Tasa de funcionamiento (pruebas)
# ==========================================
def fig_tasa_pruebas(tasa):
    """Casos de prueba y tasa de funcionamiento vs. la meta de 90 %."""
    total = tasa["casos_totales"]
    exitosos = tasa["casos_exitosos"]
    fallidos = tasa["casos_totales"] - exitosos

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.8))

    pos = np.arange(2)
    barras = ax1.bar(pos, [exitosos, fallidos], 0.55, color=[VERDE, ROJO])
    ax1.bar_label(barras, fontsize=10, padding=2)
    ax1.set_xticks(pos, ["exitosos", "fallidos +\nerrores + omitidos"], fontsize=9)
    ax1.set_ylabel("casos de prueba")
    ax1.set_ylim(0, total * 1.15)
    ax1.set_title(f"Suite de pruebas ({tasa['suite']})\n{exitosos}/{total} casos",
                  fontsize=11)
    _estilo(ax1)

    pct = tasa["tasa_funcionamiento"] * 100
    barra = ax2.bar([0], [pct], 0.5, color=VERDE if tasa["cumple"] else ROJO)
    ax2.bar_label(barra, labels=[f"{pct:.0f} %"], fontsize=11, padding=3)
    ax2.axhline(tasa["meta"] * 100, color=ROJO, linestyle="--", linewidth=1.4,
                label=f"meta I-5.3 (\u2265 {tasa['meta'] * 100:.0f} %)")
    ax2.set_xlim(-0.6, 0.6)
    ax2.set_ylim(0, 112)
    ax2.set_xticks([0], ["tasa de\nfuncionamiento"])
    ax2.set_ylabel("porcentaje")
    ax2.set_title("Tasa de funcionamiento\ncasos exitosos / totales", fontsize=11)
    ax2.legend(frameon=False, fontsize=9, loc="lower right")
    _estilo(ax2)

    fig.suptitle("I-5.3  Tasa de funcionamiento \u2014 meta \u2265 90 %",
                 fontsize=13, y=1.03)
    guardar(fig, "I-5.3_tasa_pruebas.png")


# ==========================================
# I-5.4  Disponibilidad en horario del OLTP
# ==========================================
def fig_disponibilidad(disp):
    """Pings de salud en el tiempo y disponibilidad vs. la meta de 95 %."""
    muestras = disp["muestras"]
    idx = [m["i"] for m in muestras]
    ms = [m["ms"] for m in muestras]
    ok = [m["ok"] for m in muestras]
    media = disp.get("latencia_media_ms")

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.6, 4.8),
                                   gridspec_kw={"width_ratios": [2, 1]})

    ax1.plot(idx, ms, color=AZUL, linewidth=1.2, zorder=2)
    ax1.scatter([i for i, o in zip(idx, ok) if o],
                [v for v, o in zip(ms, ok) if o], s=22, color=VERDE,
                zorder=3, label="ping OK (HTTP 200)")
    ax1.scatter([i for i, o in zip(idx, ok) if not o],
                [v for v, o in zip(ms, ok) if not o], s=40, color=ROJO,
                marker="x", zorder=3, label="ping fallido")
    if media is not None:
        ax1.axhline(media, color=NARANJA, linestyle="--", linewidth=1.2,
                    label=f"latencia media {media:.0f} ms")
    ax1.set_xlabel("numero de ping")
    ax1.set_ylabel("latencia (ms)")
    ax1.set_title(f"Monitoreo de {disp['url']}\n"
                  f"{disp['pings_ok']}/{disp['pings_totales']} pings OK en la ventana",
                  fontsize=11)
    ax1.legend(frameon=False, fontsize=8)
    _estilo(ax1)

    pct = disp["disponibilidad"] * 100
    barra = ax2.bar([0], [pct], 0.5,
                    color=VERDE if disp["cumple"] else ROJO)
    ax2.bar_label(barra, labels=[f"{pct:.0f} %"], fontsize=11, padding=3)
    ax2.axhline(disp["meta"] * 100, color=ROJO, linestyle="--", linewidth=1.4,
                label=f"meta I-5.4 (\u2265 {disp['meta'] * 100:.0f} %)")
    ax2.set_xlim(-0.6, 0.6)
    ax2.set_ylim(0, 112)
    ax2.set_xticks([0], ["disponibilidad"])
    ax2.set_ylabel("porcentaje")
    ax2.set_title("Disponibilidad\npings OK / totales", fontsize=11)
    ax2.legend(frameon=False, fontsize=9, loc="lower right")
    _estilo(ax2)

    fig.suptitle("I-5.4  Disponibilidad \u2014 meta \u2265 95 %",
                 fontsize=13, y=1.03)
    guardar(fig, "I-5.4_disponibilidad.png")


# ==========================================
# Main
# ==========================================
def main():
    os.makedirs(DIR_GRAF, exist_ok=True)
    log(f"Graficos -> {DIR_GRAF}")

    fig_calidad(leer("calidad.json"))                       # I-1.2
    fig_ranking(leer("honesto.json"))                       # I-2.1 / I-5.1
    fig_seeds(leer("seeds.json"))                           # I-2.1
    fig_correlacion(leer("../correlacion.json"))            # I-2.2
    fig_confusion(leer("clasificador_tipo.json"))           # I-3.1
    fig_topk_clasificador(leer("clasificador_tipo.json"))   # I-3.1
    fig_cuando(leer("clasificador_tipo_cuando.json"))       # I-3.1
    fig_severidad(leer("diagnostico_final.json"))           # I-3.2
    fig_efectividad(leer("diagnostico_final.json"))         # I-3.3
    fig_robustez(leer("robustez.json"), leer("latencia.json"))  # I-4.2
    fig_ttfa(leer("diagnostico_final.json"))                # I-0

    # OE5 - desempeno del sistema (I-5.x).
    ruta_tiempos = os.path.join(DIR_VAL, "tiempos_operacion.json")
    tiempos = None
    if os.path.isfile(ruta_tiempos):
        with open(ruta_tiempos, encoding="utf-8") as fh:
            tiempos = json.load(fh)
    fig_recall(leer("honesto.json"), leer("seeds.json"),
               leer("metrics.json"))                        # I-5.1
    fig_tiempos_operacion(leer("latencia.json"),
                          leer("disponibilidad.json"), tiempos)  # I-5.2
    fig_tasa_pruebas(leer("tasa_pruebas.json"))             # I-5.3
    fig_disponibilidad(leer("disponibilidad.json"))         # I-5.4

    log("Listo.")


if __name__ == "__main__":
    main()
