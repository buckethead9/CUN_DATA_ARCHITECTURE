from __future__ import annotations

from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# =========================================================
# Rutas
# =========================================================
ROOT_DIR = Path(__file__).parent.parent
OUTPUT_DIR = ROOT_DIR / "outputs"
VISUAL_DIR = OUTPUT_DIR / "visuals"
VISUAL_DIR.mkdir(parents=True, exist_ok=True)

# =========================================================
# Estilo visual
# =========================================================
RISK_COLORS = {
    "Crítico": "#D62828",
    "Moderado": "#F77F00",
    "Bajo": "#287D7D",
}

MODALITY_COLORS = {
    "V": "#2B5D8C",
    "P": "#D4A017",
}

MODALITY_LABELS = {
    "V": "Virtual",
    "P": "Presencial",
}

RISK_ORDER = ["Crítico", "Moderado", "Bajo"]

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


# =========================================================
# Utilidades
# =========================================================
def add_source(fig: plt.Figure, filename: str) -> None:
    fig.text(
        0.01,
        0.01,
        f"Fuente: outputs/{filename} · {datetime.now():%Y-%m-%d}",
        fontsize=7.5,
        color="#888888",
        ha="left",
    )


def save_figure(fig: plt.Figure, name: str) -> None:
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    fig.savefig(VISUAL_DIR / name, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"[OK] outputs/visuals/{name}")


# =========================================================
# 1. Distribución de asistencia
# =========================================================
def plot_attendance_distribution() -> None:
    filename = "tasa_asistencia_estudiante.csv"
    df = pd.read_csv(OUTPUT_DIR / filename)

    fig, ax = plt.subplots(figsize=(9, 5.5))
    bins = np.linspace(0, 1, 21)

    for modality, color in MODALITY_COLORS.items():
        subset = df.loc[df["MODALIDAD"] == modality, "TASA_ASISTENCIA"]

        ax.hist(
            subset,
            bins=bins,
            color=color,
            alpha=0.65,
            edgecolor="white",
            label=f"{MODALITY_LABELS[modality]} (n={len(subset)})",
        )

        mean_value = subset.mean()
        ax.axvline(mean_value, color=color, linestyle="--", linewidth=1.8)
        ax.text(
            mean_value,
            ax.get_ylim()[1] * 0.92,
            f"{mean_value:.1%}",
            color=color,
            fontsize=10,
            weight="bold",
            ha="center",
        )

    ax.set_title("Distribución de la Tasa de Asistencia", fontsize=15, weight="bold", pad=16)
    ax.set_xlabel("Tasa de asistencia")
    ax.set_ylabel("Cantidad de estudiantes")
    ax.xaxis.set_major_formatter(lambda x, _: f"{x:.0%}")
    ax.legend(frameon=False, loc="upper center")

    add_source(fig, filename)
    save_figure(fig, "distribucion_riesgo.png")


# =========================================================
# 2. Riesgo académico
# =========================================================
def plot_risk_categories() -> None:
    filename = "tasa_asistencia_estudiante.csv"
    df = pd.read_csv(OUTPUT_DIR / filename)

    summary = (
        df.groupby(["RIESGO", "MODALIDAD"])
        .size()
        .unstack(fill_value=0)
        .reindex(RISK_ORDER)
    )

    totals = summary.sum(axis=1)
    grand_total = totals.sum()

    fig, ax = plt.subplots(figsize=(9, 5.5))
    base = np.zeros(len(summary))

    for modality in MODALITY_COLORS:
        values = summary.get(modality, pd.Series(0, index=summary.index)).values

        ax.bar(
            summary.index,
            values,
            bottom=base,
            color=MODALITY_COLORS[modality],
            edgecolor="white",
            width=0.6,
            label=MODALITY_LABELS[modality],
        )

        base += values

    for i, risk in enumerate(summary.index):
        total = totals[risk]
        ax.text(
            i,
            total + grand_total * 0.015,
            f"{total}\n{total / grand_total:.1%}",
            ha="center",
            fontsize=11,
            weight="bold",
        )

    ax.set_title("Clasificación de Riesgo Académico", fontsize=15, weight="bold", pad=16)
    ax.set_ylabel("Número de estudiantes")
    ax.legend(frameon=False)

    add_source(fig, filename)
    save_figure(fig, "riesgo_categorias.png")


# =========================================================
# 3. Correlación asistencia vs rendimiento
# =========================================================
def plot_correlation() -> None:
    filename = "correlacion_asistencia_desempeno.csv"
    df = pd.read_csv(OUTPUT_DIR / filename)

    r_global = df["TASA_ASISTENCIA"].corr(df["NOTA_PROMEDIO"])

    fig, ax = plt.subplots(figsize=(10, 6.5))
    x_line = np.linspace(0, 1, 100)

    for modality, color in MODALITY_COLORS.items():
        subset = df[df["MODALIDAD"] == modality]

        ax.scatter(
            subset["TASA_ASISTENCIA"],
            subset["NOTA_PROMEDIO"],
            alpha=0.35,
            color=color,
            s=28,
            edgecolors="none",
            label=MODALITY_LABELS[modality],
        )

        slope, intercept = np.polyfit(subset["TASA_ASISTENCIA"], subset["NOTA_PROMEDIO"], 1)
        ax.plot(x_line, slope * x_line + intercept, color=color, linewidth=2.4)

        r_mod = subset["TASA_ASISTENCIA"].corr(subset["NOTA_PROMEDIO"])
        ax.annotate(
            f"r={r_mod:.2f}",
            xy=(1.0, slope + intercept),
            xytext=(1.02, slope + intercept),
            color=color,
            fontsize=10,
            weight="bold",
            va="center",
        )

    ax.text(
        0.02,
        0.98,
        f"Correlación global de Pearson: r = {r_global:.3f}",
        transform=ax.transAxes,
        fontsize=10,
        weight="bold",
        va="top",
        bbox=dict(facecolor="white", edgecolor="#D62828", boxstyle="round,pad=0.5"),
    )

    ax.set_title("Asistencia vs. Rendimiento Académico", fontsize=15, weight="bold", pad=16)
    ax.set_xlabel("Tasa de asistencia")
    ax.set_ylabel("Promedio de nota")
    ax.xaxis.set_major_formatter(lambda x, _: f"{x:.0%}")
    ax.set_xlim(-0.03, 1.12)
    ax.legend(frameon=False, loc="lower right")

    add_source(fig, filename)
    save_figure(fig, "correlacion_rendimiento.png")


# =========================================================
# 4. Ranking de sesiones
# =========================================================
def plot_session_ranking() -> None:
    filename = "ranking_sesiones_top15.csv"
    df = pd.read_csv(OUTPUT_DIR / filename)

    fig, axes = plt.subplots(1, 2, figsize=(13, 6.5))

    configs = [
        ("MAYOR_PARTICIPACION", "#287D7D", "Mayor participación"),
        ("MENOR_PARTICIPACION", "#D62828", "Menor participación"),
    ]

    for ax, (ranking_type, color, title) in zip(axes, configs):
        data = df[df["RANKING"] == ranking_type].sort_values(
            "TASA_ASISTENCIA",
            ascending=(ranking_type == "MENOR_PARTICIPACION"),
        )

        bars = ax.barh(data["UID_SESION"], data["TASA_ASISTENCIA"], color=color, height=0.65)
        ax.invert_yaxis()
        ax.set_title(title, fontsize=13, weight="bold")
        ax.xaxis.set_major_formatter(lambda x, _: f"{x:.0%}")
        ax.set_xlim(0, 1.12)

        for bar, (_, row) in zip(bars, data.iterrows()):
            ax.text(
                bar.get_width() + 0.02,
                bar.get_y() + bar.get_height() / 2,
                f"{row.TASA_ASISTENCIA:.0%}",
                va="center",
                fontsize=8.5,
            )

    fig.suptitle("Sesiones con Mayor y Menor Participación", fontsize=15, weight="bold", y=1.02)

    add_source(fig, filename)
    save_figure(fig, "top_sesiones.png")


# =========================================================
# Ejecución
# =========================================================
def main() -> None:
    plot_attendance_distribution()
    plot_risk_categories()
    plot_correlation()
    plot_session_ranking()

    print("\nVisuales generados en outputs/visuals/")


if __name__ == "__main__":
    main()
