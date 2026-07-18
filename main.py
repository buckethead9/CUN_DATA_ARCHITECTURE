from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final, Sequence

import numpy as np
import pandas as pd

# =========================================================
# Configuración
# =========================================================
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

ROOT_DIR: Final[Path] = Path(__file__).parent
CORE_DIR: Final[Path] = ROOT_DIR / "data" / "core"
STAGING_DIR: Final[Path] = ROOT_DIR / "data" / "staging"
LOGS_DIR: Final[Path] = ROOT_DIR / "data" / "logs"
OUTPUT_DIR: Final[Path] = ROOT_DIR / "outputs"

MIN_GRADE: Final[float] = 0.0
MAX_GRADE: Final[float] = 5.0
CRITICAL_RISK: Final[float] = 0.40
MODERATE_RISK: Final[float] = 0.70
NO_CODE: Final[str] = "SIN_CODIGO_DISPONIBLE"

TRAMO_LIMITS: Final[list[float]] = [
    -float("inf"),
    1.0,
    2.0,
    3.0,
    4.0,
    4.5,
    MAX_GRADE,
]

TRAMO_LABELS: Final[list[str]] = [
    "NULO_PLAG",
    "DEFICIENTE",
    "INSUFICIENTE",
    "ACEPTABLE",
    "SOBRESALIENTE",
    "EXCELENTE",
]

VIRTUAL_MAP: Final[dict[str, str]] = {
    "QUIZ_1": "QUIZ1",
    "PARCIAL_1": "PARCIAL1",
    "PARCIAL_2": "PARCIAL2",
    "QUIZ_2": "QUIZ2",
    "QUIZ_3": "QUIZ3",
    "AUTOEVALUACION": "AUTO",
    "COEVALUACION": "COE",
    "ACA_FINAL": "PROY_FINAL",
}

PRESENTIAL_MAP: Final[dict[str, str]] = {
    "QUIZ_1": "QUIZ1",
    "IDEA": "IDEA",
    "PARCIAL_1": "PARCIAL1",
    "DEBATE": "DEBATE",
    "PROY_DES": "PROY_DES",
    "PITCH": "PITCH",
    "QUIZ_2": "QUIZ2",
    "AUTOEVALUACION": "AUTO",
    "COEVALUACION": "COE",
    "ACA_FINAL": "FINAL",
}

OUTPUT_COLUMNS: Final[list[str]] = [
    "UID_SESION",
    "CLAVE_UNICA_ESTUDIANTE",
    "UID_ACTIVIDAD",
    "NOTA_CUANTITATIVA",
    "IMPACTO_REAL",
    "COD_FEEDBACK",
    "COD_FEEDBACK_ESTIMADO",
]


# =========================================================
# Utilidades
# =========================================================
def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    translation = str.maketrans("ÁÉÍÓÚÑ", "AEIOUN")
    df = df.copy()
    df.columns = [c.strip().upper().translate(translation) for c in df.columns]
    return df


def clean_student_id(value: object) -> str:
    text = str(value).strip()
    return text[:-2] if text.endswith(".0") else text


def read_csv(path: Path, **kwargs: object) -> pd.DataFrame:
    try:
        return pd.read_csv(path, **kwargs)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"No se encontró '{path}'.") from exc


# =========================================================
# Ingesta
# =========================================================
def load_grades_matrix(path: Path) -> pd.DataFrame:
    df = normalize_columns(read_csv(path))
    df = df.dropna(subset=["ID_ESTUDIANTE"]).reset_index(drop=True)
    df["ID_ESTUDIANTE"] = df["ID_ESTUDIANTE"].apply(clean_student_id)
    return df


# =========================================================
# Transformación
# =========================================================
def unpivot_matrix(df: pd.DataFrame, modality: str, mapping: dict[str, str]) -> pd.DataFrame:
    temp = df.copy()
    temp["MATERIA"] = temp["UID_GRUPO"].str.rsplit("_", n=1).str[0]
    temp["GRUPO_NUM"] = temp["UID_GRUPO"].str.rsplit("_", n=1).str[1]
    temp["CLAVE_UNICA_ESTUDIANTE"] = temp["ID_ESTUDIANTE"] + "_" + temp["GRUPO_NUM"]

    activity_cols = [c for c in mapping if c in temp.columns]

    long_df = temp.melt(
        id_vars=["UID_GRUPO", "CLAVE_UNICA_ESTUDIANTE", "MATERIA"],
        value_vars=activity_cols,
        var_name="COL_ORIGEN",
        value_name="NOTA_CUANTITATIVA",
    )

    long_df["ACTIVIDAD"] = long_df["COL_ORIGEN"].map(mapping)
    long_df["MODALIDAD"] = modality

    return long_df.drop(columns="COL_ORIGEN")


# =========================================================
# Normalización matemática
# =========================================================
def calculate_impact(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    result["IMPACTO_REAL"] = (
        result["NOTA_CUANTITATIVA"] * result["PESO"]
    ).round(4)
    return result


# =========================================================
# Motor DRM
# =========================================================
def build_feedback_table(dictionary: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, str]] = []

    for subject, group in dictionary.groupby("MATERIA"):
        rows.extend([
            {"MATERIA": subject, "TRAMO": "NULO_PLAG", "COD_FEEDBACK_ESTIMADO": "GEN_NULO|GEN_PLAG"},
            {"MATERIA": subject, "TRAMO": "DEFICIENTE", "COD_FEEDBACK_ESTIMADO": "|".join(group[group["COEF_IMPACTO"] == 0.20]["COD_FEEDBACK"]) or NO_CODE},
            {"MATERIA": subject, "TRAMO": "INSUFICIENTE", "COD_FEEDBACK_ESTIMADO": "|".join(group[group["COEF_IMPACTO"].between(0.40, 0.50)]["COD_FEEDBACK"]) or NO_CODE},
            {"MATERIA": subject, "TRAMO": "ACEPTABLE", "COD_FEEDBACK_ESTIMADO": "|".join(group[group["COEF_IMPACTO"].between(0.60, 0.70)]["COD_FEEDBACK"]) or NO_CODE},
            {"MATERIA": subject, "TRAMO": "SOBRESALIENTE", "COD_FEEDBACK_ESTIMADO": "|".join([*group[group["COEF_IMPACTO"] == 0.80]["COD_FEEDBACK"], "GEN_TARD"]) or NO_CODE},
            {"MATERIA": subject, "TRAMO": "EXCELENTE", "COD_FEEDBACK_ESTIMADO": "GEN_OK"},
        ])

    return pd.DataFrame(rows)


# =========================================================
# Orquestación
# =========================================================
def run_pipeline() -> pd.DataFrame:
    OUTPUT_DIR.mkdir(exist_ok=True)

    log.info("Cargando datos...")
    virtual = load_grades_matrix(STAGING_DIR / "CALIFICACIONES_VIRTUAL.csv")
    presencial = load_grades_matrix(STAGING_DIR / "CALIFICACIONES_PRESENCIAL.csv")
    activities = read_csv(CORE_DIR / "ACTIVIDADES.csv", dtype={"NUM_SESION": str})
    sessions = read_csv(CORE_DIR / "REGISTRO_SESIONES.csv")
    dictionary = read_csv(CORE_DIR / "DICCIONARIO_FEEDBACK.csv")

    log.info("Transformando matrices...")
    long_df = pd.concat([
        unpivot_matrix(virtual, "V", VIRTUAL_MAP),
        unpivot_matrix(presencial, "P", PRESENTIAL_MAP),
    ], ignore_index=True)

    log.info("Enriqueciendo con actividades...")
    enriched = long_df.merge(
        activities,
        on=["MATERIA", "MODALIDAD", "ACTIVIDAD"],
        how="left",
    )

    log.info("Enriqueciendo con sesiones...")
    session_dim = sessions[["UID_GRUPO", "SESION", "UID_SESION"]].copy()
    session_dim["SESION"] = session_dim["SESION"].astype(int).astype(str)

    enriched = enriched.merge(
        session_dim,
        left_on=["UID_GRUPO", "NUM_SESION"],
        right_on=["UID_GRUPO", "SESION"],
        how="left",
    )

    enriched = calculate_impact(enriched)

    log.info("Aplicando motor DRM...")
    feedback_table = build_feedback_table(dictionary)

    enriched["TRAMO"] = pd.cut(
        enriched["NOTA_CUANTITATIVA"],
        bins=TRAMO_LIMITS,
        labels=TRAMO_LABELS,
    )

    enriched = enriched.merge(feedback_table, on=["MATERIA", "TRAMO"], how="left")
    enriched.drop(columns="TRAMO", inplace=True)

    enriched["COD_FEEDBACK"] = pd.NA

    final_df = enriched[OUTPUT_COLUMNS]

    output_path = OUTPUT_DIR / "LOG_TRANSACCIONAL_FEEDBACK.csv"
    final_df.to_csv(output_path, index=False)

    log.info("Archivo generado: %s", output_path)
    log.info("Registros procesados: %d", len(final_df))

    return final_df


# =========================================================
# Ejecución
# =========================================================
def main() -> None:
    try:
        result = run_pipeline()
    except (FileNotFoundError, ValueError) as exc:
        log.error("Pipeline detenido: %s", exc)
        raise SystemExit(1) from exc

    total = len(result)
    ok = int((result["COD_FEEDBACK_ESTIMADO"] == "GEN_OK").sum())

    log.info("Resumen: %d filas | GEN_OK: %d (%.1f%%)", total, ok, 100 * ok / total)


if __name__ == "__main__":
    main()
