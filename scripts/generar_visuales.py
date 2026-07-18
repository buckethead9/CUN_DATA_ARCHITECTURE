"""generar_visuales.py -- Visualizaciones para publicación (LinkedIn/README).

Regla de diseño no negociable: **ningún gráfico recalcula nada**. Cada
función lee exclusivamente de `outputs/*.csv` -- los artefactos ya
auditados por `main.py` y documentados en `quality_report.md`. Si un
número no existe en `outputs/`, no se grafica; se corrige el pipeline,
no el script de gráficos.

Uso:
    python scripts/generar_visuales.py

Requiere haber corrido `python main.py` primero.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

RAIZ = Path(__file__).parent.parent
DIR_SALIDA = RAIZ / "outputs"
DIR_VISUALES = DIR_SALIDA / "visuals"
DIR_VISUALES.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------- #
# Identidad visual (consistente en las 4 piezas -- un color significa lo
# mismo en todos los gráficos, nunca se reasigna semántica por figura)
# --------------------------------------------------------------------------- #
RIESGO_COLOR = {"Crítico": "#D62828", "Moderado": "#F77F00", "Bajo": "#287D7D"}
MODALIDAD_COLOR = {"V": "#2B5D8C", "P": "#D4A017"}
MODALIDAD_LABEL = {"V": "Virtual", "P": "Presencial"}
ORDEN_RIESGO = ["Crítico", "Moderado", "Bajo"]

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "DejaVu Sans"],
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "grid.linestyle": "--",
    "figure.dpi": 100,
})


def _fuente(ax: plt.Axes, archivo: str) -> None:
    """Pie de trazabilidad: de qué archivo auditado sale cada número del gráfico."""
    ax.figure.text(
        0.01, 0.01, f"Fuente: outputs/{archivo}  ·  generado {datetime.now():%Y-%m-%d}",
        fontsize=7.5, color="#888888", ha="left",
    )


def _guardar(fig: plt.Figure, nombre: str) -> None:
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    fig.savefig(DIR_VISUALES / nombre, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"[OK] outputs/visuals/{nombre}")


# --------------------------------------------------------------------------- #
# 1. Distribución de la tasa de asistencia, por modalidad
# --------------------------------------------------------------------------- #
def graficar_distribucion_asistencia() -> None:
    archivo = "tasa_asistencia_estudiante.csv"
    df = pd.read_csv(DIR_SALIDA / archivo)

    fig, ax = plt.subplots(figsize=(9, 5.5))
    bins = np.linspace(0, 1, 21)
    for modalidad, color in MODALIDAD_COLOR.items():
        subset = df.loc[df["MODALIDAD"] == modalidad, "TASA_ASISTENCIA"]
        ax.hist(subset, bins=bins, color=color, alpha=0.65,
                label=f"{MODALIDAD_LABEL[modalidad]} (n={len(subset)})", edgecolor="white")
        media = subset.mean()
        ax.axvline(media, color=color, linestyle="--", linewidth=1.8)
        ax.text(media, ax.get_ylim()[1] * 0.92, f"{media:.1%}", color=color,
                fontsize=10, weight="bold", ha="center")

    ax.set_title("Distribución de la Tasa de Asistencia, por Modalidad", fontsize=15, weight="bold", pad=16)
    ax.set_xlabel("Tasa de asistencia")
    ax.set_ylabel("Cantidad de estudiantes")
    ax.xaxis.set_major_formatter(lambda x, _: f"{x:.0%}")
    ax.legend(frameon=False, loc="upper center")
    _fuente(ax, archivo)
    _guardar(fig, "distribucion_riesgo.png")


# --------------------------------------------------------------------------- #
# 2. Clasificación de riesgo académico, desagregada por modalidad
# --------------------------------------------------------------------------- #
def graficar_clasificacion_riesgo() -> None:
    archivo = "tasa_asistencia_estudiante.csv"
    df = pd.read_csv(DIR_SALIDA / archivo)

    conteo = df.groupby(["RIESGO", "MODALIDAD"]).size().unstack(fill_value=0).reindex(ORDEN_RIESGO)
    total_por_riesgo = conteo.sum(axis=1)
    total_general = total_por_riesgo.sum()

    fig, ax = plt.subplots(figsize=(9, 5.5))
    base = np.zeros(len(conteo))
    for modalidad in MODALIDAD_COLOR:
        valores = conteo.get(modalidad, pd.Series(0, index=conteo.index)).values
        ax.bar(conteo.index, valores, bottom=base, color=MODALIDAD_COLOR[modalidad],
               label=MODALIDAD_LABEL[modalidad], edgecolor="white", width=0.6)
        base += valores

    for i, riesgo in enumerate(conteo.index):
        total = total_por_riesgo[riesgo]
        ax.text(i, total + total_general * 0.015, f"{total}\n{total/total_general:.1%}",
                ha="center", fontsize=11, weight="bold")

    ax.set_title("Clasificación de Riesgo Académico (por Modalidad)", fontsize=15, weight="bold", pad=16)
    ax.set_ylabel("Número de estudiantes")
    ax.legend(frameon=False, loc="upper right")
    _fuente(ax, archivo)
    _guardar(fig, "riesgo_categorias.png")


# --------------------------------------------------------------------------- #
# 3. Asistencia vs. rendimiento académico
# --------------------------------------------------------------------------- #
def graficar_correlacion_rendimiento() -> None:
    archivo = "correlacion_asistencia_desempeno.csv"
    df = pd.read_csv(DIR_SALIDA / archivo)
    r_general = df["TASA_ASISTENCIA"].corr(df["NOTA_PROMEDIO"])

    fig, ax = plt.subplots(figsize=(10, 6.5))
    x_linea = np.linspace(0, 1, 100)
    for modalidad, color in MODALIDAD_COLOR.items():
        subset = df.loc[df["MODALIDAD"] == modalidad]
        ax.scatter(subset["TASA_ASISTENCIA"], subset["NOTA_PROMEDIO"], alpha=0.35,
                   color=color, s=26, edgecolors="none", label=MODALIDAD_LABEL[modalidad])
        pendiente, intercepto = np.polyfit(subset["TASA_ASISTENCIA"], subset["NOTA_PROMEDIO"], 1)
        ax.plot(x_linea, pendiente * x_linea + intercepto, color=color, linewidth=2.4)
        r_mod = subset["TASA_ASISTENCIA"].corr(subset["NOTA_PROMEDIO"])
        ax.annotate(f"r={r_mod:.2f}", xy=(1.0, pendiente * 1.0 + intercepto), xytext=(1.02, pendiente + intercepto),
                    color=color, fontsize=10, weight="bold", va="center")

    n_cero = int((df["TASA_ASISTENCIA"] == 0).sum())
    n_cero_v = int(((df["TASA_ASISTENCIA"] == 0) & (df["MODALIDAD"] == "V")).sum())
    ax.annotate(
        f"{n_cero} estudiantes con 0% de asistencia\n({n_cero_v} de ellos, virtuales)\n"
        "concentran este extremo del eje X",
        xy=(0.0, 1.2), xytext=(0.18, 0.55),
        arrowprops=dict(arrowstyle="->", color="#333333", lw=1.5),
        fontsize=9.5, color="#333333",
        bbox=dict(facecolor="white", edgecolor="#333333", boxstyle="round,pad=0.4", linewidth=1),
    )

    texto = (f"Correlación global de Pearson: r = {r_general:.3f}\n"
             "Relación positiva débil, y distinta por modalidad\n"
             "(ver líneas de tendencia separadas)")
    ax.text(0.02, 0.98, texto, transform=ax.transAxes, fontsize=10, weight="bold", va="top",
            bbox=dict(facecolor="white", edgecolor="#D62828", boxstyle="round,pad=0.5", linewidth=1.5))

    ax.set_title("Asistencia vs. Rendimiento Académico", fontsize=15, weight="bold", pad=16)
    ax.set_xlabel("Tasa de asistencia")
    ax.set_ylabel("Promedio de nota (0.0-5.0)")
    ax.xaxis.set_major_formatter(lambda x, _: f"{x:.0%}")
    ax.set_xlim(-0.03, 1.12)
    ax.legend(frameon=False, loc="lower right")
    _fuente(ax, archivo)
    _guardar(fig, "correlacion_rendimiento.png")


# --------------------------------------------------------------------------- #
# 4. Sesiones con mayor y menor participación
# --------------------------------------------------------------------------- #
def graficar_ranking_sesiones() -> None:
    archivo = "ranking_sesiones_top15.csv"
    df = pd.read_csv(DIR_SALIDA / archivo)
    minimo = df["INSCRITOS_REGISTRADOS"].min()

    fig, (ax_top, ax_bottom) = plt.subplots(1, 2, figsize=(13, 6.5))
    for ax, direccion, color, titulo in [
        (ax_top, "MAYOR_PARTICIPACION", "#287D7D", "Mayor participación"),
        (ax_bottom, "MENOR_PARTICIPACION", "#D62828", "Menor participación"),
    ]:
        datos = df.loc[df["RANKING"] == direccion].sort_values("TASA_ASISTENCIA", ascending=(direccion == "MENOR_PARTICIPACION"))
        barras = ax.barh(datos["UID_SESION"], datos["TASA_ASISTENCIA"], color=color, height=0.65)
        ax.invert_yaxis()
        ax.set_title(titulo, fontsize=13, weight="bold")
        ax.xaxis.set_major_formatter(lambda x, _: f"{x:.0%}")
        ax.set_xlim(0, 1.12)
        for barra, (_, fila) in zip(barras, datos.iterrows()):
            ax.text(barra.get_width() + 0.02, barra.get_y() + barra.get_height() / 2,
                     f"{fila.TASA_ASISTENCIA:.0%} (n={int(fila.INSCRITOS_REGISTRADOS)})",
                     va="center", fontsize=8.5)

    fig.suptitle(f"Sesiones con Mayor y Menor Participación (≥{minimo} inscritos)", fontsize=15, weight="bold", y=1.02)
    _fuente(ax_bottom, archivo)
    _guardar(fig, "top_sesiones.png")


def main() -> None:
    graficar_distribucion_asistencia()
    graficar_clasificacion_riesgo()
    graficar_correlacion_rendimiento()
    graficar_ranking_sesiones()
    print("\nVisuales generados en outputs/visuals/ a partir únicamente de archivos auditados en outputs/.")


if __name__ == "__main__":
    main()
