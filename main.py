"""Motor ETL -- Ledger Docente CUN 2026.

Consolida CALIFICACIONES_VIRTUAL / CALIFICACIONES_PRESENCIAL (staging, formato
ancho) en LOG_TRANSACCIONAL_FEEDBACK (hechos, formato largo), validando
integridad referencial contra las dimensiones REGISTRO_ESTUDIANTES,
REGISTRO_SESIONES, ACTIVIDADES y DICCIONARIO_FEEDBACK. Genera además el
análisis longitudinal de asistencia y el reporte de calidad de datos.

Uso:
    python main.py

Estructura de datos esperada (ver README.md):
    data/staging/CALIFICACIONES_VIRTUAL.csv, CALIFICACIONES_PRESENCIAL.csv
    data/core/ACTIVIDADES.csv, DICCIONARIO_FEEDBACK.csv,
              REGISTRO_ESTUDIANTES.csv, REGISTRO_SESIONES.csv
    data/logs/LOG_ASISTENCIA.csv

Salidas en outputs/:
    LOG_TRANSACCIONAL_FEEDBACK.csv, quality_report.md,
    tasa_asistencia_sesion.csv, tasa_asistencia_estudiante.csv,
    estudiantes_riesgo.csv, ranking_sesiones.csv
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Final, Sequence

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Configuración
# --------------------------------------------------------------------------- #
RAIZ: Final[Path] = Path(__file__).parent
DIR_CORE: Final[Path] = RAIZ / "data" / "core"
DIR_STAGING: Final[Path] = RAIZ / "data" / "staging"
DIR_LOGS: Final[Path] = RAIZ / "data" / "logs"
DIR_SALIDA: Final[Path] = RAIZ / "outputs"

NOTA_MIN: Final[float] = 0.0
NOTA_MAX: Final[float] = 5.0
LIMITE_RIESGO_CRITICO: Final[float] = 0.40
LIMITE_RIESGO_MODERADO: Final[float] = 0.70
SIN_CODIGO: Final[str] = "SIN_CODIGO_DISPONIBLE"

# Tramos DRM: bandas fijas (no percentiles), límite superior, intervalo (a, b].
LIMITES_TRAMO: Final[list[float]] = [-float("inf"), 1.0, 2.0, 3.0, 4.0, 4.5, NOTA_MAX]
ETIQUETAS_TRAMO: Final[list[str]] = [
    "NULO_PLAG", "DEFICIENTE", "INSUFICIENTE", "ACEPTABLE", "SOBRESALIENTE", "EXCELENTE",
]

# 'ACA_FINAL' resuelve a una actividad distinta según modalidad (ver README).
MAPA_VIRTUAL: Final[dict[str, str]] = {
    "QUIZ_1": "QUIZ1", "PARCIAL_1": "PARCIAL1", "PARCIAL_2": "PARCIAL2",
    "QUIZ_2": "QUIZ2", "QUIZ_3": "QUIZ3", "AUTOEVALUACION": "AUTO",
    "COEVALUACION": "COE", "ACA_FINAL": "PROY_FINAL",
}
MAPA_PRESENCIAL: Final[dict[str, str]] = {
    "QUIZ_1": "QUIZ1", "IDEA": "IDEA", "PARCIAL_1": "PARCIAL1", "DEBATE": "DEBATE",
    "PROY_DES": "PROY_DES", "PITCH": "PITCH", "QUIZ_2": "QUIZ2",
    "AUTOEVALUACION": "AUTO", "COEVALUACION": "COE", "ACA_FINAL": "FINAL",
}

COLUMNAS_SALIDA: Final[list[str]] = [
    "UID_SESION", "CLAVE_UNICA_ESTUDIANTE", "UID_ACTIVIDAD",
    "NOTA_CUANTITATIVA", "IMPACTO_REAL", "COD_FEEDBACK", "COD_FEEDBACK_ESTIMADO",
]


# --------------------------------------------------------------------------- #
# 1. Ingesta y limpieza
# --------------------------------------------------------------------------- #
def normalizar_columnas(df: pd.DataFrame) -> pd.DataFrame:
    """Encabezados en mayúsculas, sin tildes ni espacios sobrantes.

    Evita que una fuente acentuada de forma distinta ('AUTOEVALUACIÓN' vs.
    'AUTOEVALUACION') rompa silenciosamente un merge o un mapeo de columnas.
    """
    tabla = str.maketrans("ÁÉÍÓÚÑ", "AEIOUN")
    df = df.copy()
    df.columns = [c.strip().upper().translate(tabla) for c in df.columns]
    return df


def limpiar_id_estudiante(valor: object) -> str:
    """Normaliza ID_ESTUDIANTE a texto sin decimales (corrige floats de Sheets)."""
    texto = str(valor).strip()
    return texto[:-2] if texto.endswith(".0") else texto


def eliminar_filas_vacias(df: pd.DataFrame, columna_clave: str) -> pd.DataFrame:
    """Descarta filas sin valor en `columna_clave` (registros en blanco del export)."""
    return df.dropna(subset=[columna_clave]).reset_index(drop=True)


def cargar_matriz_calificaciones(ruta: Path) -> pd.DataFrame:
    df = normalizar_columnas(pd.read_csv(ruta))
    df = eliminar_filas_vacias(df, "ID_ESTUDIANTE")
    df["ID_ESTUDIANTE"] = df["ID_ESTUDIANTE"].apply(limpiar_id_estudiante)
    return df


# --------------------------------------------------------------------------- #
# 2. Transformación (unpivot)
# --------------------------------------------------------------------------- #
def unpivotar_matriz(matriz: pd.DataFrame, modalidad: str, mapa_columnas: dict[str, str]) -> pd.DataFrame:
    """Ancho -> largo. Produce CLAVE_UNICA_ESTUDIANTE, ACTIVIDAD, NOTA_CUANTITATIVA, MODALIDAD."""
    df = matriz.copy()
    df["MATERIA"] = df["UID_GRUPO"].str.rsplit("_", n=1).str[0]
    df["GRUPO_NUM"] = df["UID_GRUPO"].str.rsplit("_", n=1).str[1]
    df["CLAVE_UNICA_ESTUDIANTE"] = df["ID_ESTUDIANTE"] + "_" + df["GRUPO_NUM"]

    columnas_actividad = [c for c in mapa_columnas if c in df.columns]
    largo = df.melt(
        id_vars=["UID_GRUPO", "CLAVE_UNICA_ESTUDIANTE", "MATERIA"],
        value_vars=columnas_actividad,
        var_name="COL_ORIGEN",
        value_name="NOTA_CUANTITATIVA",
    )
    largo["ACTIVIDAD"] = largo["COL_ORIGEN"].map(mapa_columnas)
    largo["MODALIDAD"] = modalidad
    return largo.drop(columns="COL_ORIGEN")


# --------------------------------------------------------------------------- #
# 3. Enriquecimiento (merges)
# --------------------------------------------------------------------------- #
def enriquecer_con_actividades(hechos: pd.DataFrame, actividades: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Merge 1: resuelve UID_ACTIVIDAD, NUM_SESION y PESO por (MATERIA, MODALIDAD, ACTIVIDAD).

    Nunca se reconstruye UID_ACTIVIDAD concatenando texto: el prefijo de
    modalidad no es consistente entre materias (ej. 'IOP_' vs. 'AL_' sin
    sufijo), así que el join contra el catálogo es la única resolución robusta.

    Retorna (hechos_enriquecidos, huerfanas) -- huerfanas son combinaciones
    sin entrada en el catálogo; se excluyen del resultado principal.
    """
    hechos = hechos.merge(actividades, on=["MATERIA", "MODALIDAD", "ACTIVIDAD"], how="left")
    huerfanas_mask = hechos["UID_ACTIVIDAD"].isna()
    huerfanas = hechos.loc[huerfanas_mask, ["MATERIA", "MODALIDAD", "ACTIVIDAD"]].drop_duplicates()
    return hechos.loc[~huerfanas_mask].copy(), huerfanas


def enriquecer_con_sesiones(hechos: pd.DataFrame, sesiones: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Merge 2: resuelve UID_SESION cruzando (UID_GRUPO, NUM_SESION) contra REGISTRO_SESIONES.

    Retorna (hechos_enriquecidos, huerfanas). Una fila "huérfana" es una
    combinación grupo+sesión que el catálogo de actividades espera pero que
    no existe como sesión real -- se conserva en la salida con un UID_SESION
    de respaldo (concatenación literal) para no perder la calificación, y se
    documenta en el reporte de calidad para que se investigue la causa.
    """
    dim = sesiones[["UID_GRUPO", "SESION", "UID_SESION"]].copy()
    dim["SESION"] = dim["SESION"].astype(int).astype(str)

    hechos = hechos.merge(dim, left_on=["UID_GRUPO", "NUM_SESION"], right_on=["UID_GRUPO", "SESION"], how="left")
    huerfanas_mask = hechos["UID_SESION"].isna()
    huerfanas = hechos.loc[huerfanas_mask, ["UID_GRUPO", "NUM_SESION", "UID_ACTIVIDAD"]].drop_duplicates()

    respaldo = hechos["UID_GRUPO"] + "_" + hechos["NUM_SESION"]
    hechos["UID_SESION"] = hechos["UID_SESION"].fillna(respaldo)
    hechos["_SESION_HUERFANA"] = huerfanas_mask
    return hechos.drop(columns="SESION"), huerfanas


# --------------------------------------------------------------------------- #
# 4. Normalización matemática
# --------------------------------------------------------------------------- #
def calcular_impacto_real(hechos: pd.DataFrame) -> pd.DataFrame:
    """IMPACTO_REAL = NOTA_CUANTITATIVA * PESO."""
    hechos = hechos.copy()
    hechos["IMPACTO_REAL"] = (hechos["NOTA_CUANTITATIVA"] * hechos["PESO"]).round(4)
    return hechos


# --------------------------------------------------------------------------- #
# 5. Motor de estimación DRM (bandas fijas, no percentiles)
# --------------------------------------------------------------------------- #
def _codigos_a_cadena(subconjunto: pd.DataFrame, adicionales: Sequence[str] = ()) -> str:
    codigos = [*subconjunto["COD_FEEDBACK"], *adicionales]
    return "|".join(codigos) if codigos else SIN_CODIGO


def construir_tabla_estimacion(diccionario: pd.DataFrame) -> pd.DataFrame:
    """Precalcula, por (MATERIA, TRAMO), los códigos candidatos -- una sola
    pasada sobre el diccionario (~37 filas) en vez de refiltrar por cada
    fila de la tabla de hechos."""
    filas: list[dict[str, str]] = []
    for materia, grupo in diccionario.groupby("MATERIA"):
        tramos = {
            "NULO_PLAG": "GEN_NULO|GEN_PLAG",
            "DEFICIENTE": _codigos_a_cadena(grupo[grupo["COEF_IMPACTO"] == 0.20]),
            "INSUFICIENTE": _codigos_a_cadena(grupo[grupo["COEF_IMPACTO"].between(0.40, 0.50)]),
            "ACEPTABLE": _codigos_a_cadena(grupo[grupo["COEF_IMPACTO"].between(0.60, 0.70)]),
            "SOBRESALIENTE": _codigos_a_cadena(grupo[grupo["COEF_IMPACTO"] == 0.80], adicionales=["GEN_TARD"]),
            "EXCELENTE": "GEN_OK",
        }
        filas.extend({"MATERIA": materia, "TRAMO": t, "COD_FEEDBACK_ESTIMADO": c} for t, c in tramos.items())
    return pd.DataFrame(filas)


def aplicar_motor_estimacion(hechos: pd.DataFrame, diccionario: pd.DataFrame) -> pd.DataFrame:
    """Asigna COD_FEEDBACK_ESTIMADO como lista de candidatos, no diagnóstico
    final: varios códigos de una materia pueden compartir COEF_IMPACTO."""
    tabla = construir_tabla_estimacion(diccionario)
    hechos = hechos.copy()
    hechos["TRAMO"] = pd.cut(hechos["NOTA_CUANTITATIVA"], bins=LIMITES_TRAMO, labels=ETIQUETAS_TRAMO)
    hechos = hechos.merge(tabla, on=["MATERIA", "TRAMO"], how="left")
    return hechos.drop(columns="TRAMO")


# --------------------------------------------------------------------------- #
# Validaciones de calidad
# --------------------------------------------------------------------------- #
def validar_estudiantes(hechos: pd.DataFrame, estudiantes: pd.DataFrame) -> pd.DataFrame:
    """CLAVE_UNICA_ESTUDIANTE presentes en `hechos` sin fila en el maestro."""
    validas = set(estudiantes["CLAVE_UNICA"])
    faltantes = sorted(set(hechos["CLAVE_UNICA_ESTUDIANTE"]) - validas)
    return pd.DataFrame({"CLAVE_UNICA_ESTUDIANTE": faltantes})


def validar_rango_notas(hechos: pd.DataFrame) -> pd.DataFrame:
    """Filas con NOTA_CUANTITATIVA fuera de [NOTA_MIN, NOTA_MAX]."""
    fuera_de_rango = ~hechos["NOTA_CUANTITATIVA"].between(NOTA_MIN, NOTA_MAX)
    return hechos.loc[fuera_de_rango, ["CLAVE_UNICA_ESTUDIANTE", "UID_ACTIVIDAD", "NOTA_CUANTITATIVA"]]


def detectar_duplicados(hechos: pd.DataFrame) -> pd.DataFrame:
    """Duplicados exactos por la llave natural de la tabla de hechos."""
    llave = ["UID_SESION", "CLAVE_UNICA_ESTUDIANTE", "UID_ACTIVIDAD"]
    return hechos.loc[hechos.duplicated(subset=llave, keep=False)].sort_values(llave)


@dataclass
class ReporteCalidad:
    total_filas: int
    filas_validas: int
    actividades_huerfanas: pd.DataFrame
    sesiones_huerfanas: pd.DataFrame
    estudiantes_huerfanos: pd.DataFrame
    notas_fuera_de_rango: pd.DataFrame
    duplicados_exactos: pd.DataFrame
    codigos_sin_cobertura: int

    @property
    def porcentaje_valido(self) -> float:
        return 100 * self.filas_validas / self.total_filas if self.total_filas else 100.0

    def _seccion(self, titulo: str, detalle: pd.DataFrame, vacio: str) -> str:
        if detalle.empty:
            return f"## {titulo}\n\n{vacio}\n"
        return f"## {titulo}\n\n{len(detalle)} encontrados.\n\n{detalle.head(20).to_markdown(index=False)}\n"

    def render_markdown(self) -> str:
        secciones = [
            f"# Reporte de Calidad de Datos\n\nGenerado: {datetime.now():%Y-%m-%d %H:%M}\n",
            "## Resumen\n\n"
            f"- Total de filas procesadas: **{self.total_filas}**\n"
            f"- Registros válidos: **{self.filas_validas}** ({self.porcentaje_valido:.1f}%)\n"
            f"- Filas sin código de auditoría estimable: **{self.codigos_sin_cobertura}**\n",
            self._seccion("Actividades sin correspondencia en ACTIVIDADES", self.actividades_huerfanas,
                          "Ninguna. Todas las columnas de las matrices de origen resolvieron a un UID_ACTIVIDAD."),
            self._seccion("Sesiones huérfanas (UID_SESION sin fila en REGISTRO_SESIONES)", self.sesiones_huerfanas,
                          "Ninguna. Toda combinación grupo+sesión esperada existe en REGISTRO_SESIONES."),
            self._seccion("Estudiantes inexistentes (CLAVE_UNICA_ESTUDIANTE sin fila en REGISTRO_ESTUDIANTES)",
                          self.estudiantes_huerfanos, "Ninguno. Todo estudiante en las calificaciones está en el maestro."),
            self._seccion(f"Notas fuera de rango [{NOTA_MIN}, {NOTA_MAX}]", self.notas_fuera_de_rango,
                          "Ninguna. Todas las notas están dentro de la escala."),
            self._seccion("Duplicados exactos", self.duplicados_exactos, "Ninguno."),
        ]
        return "\n".join(secciones)


def construir_reporte_calidad(
    hechos_validados: pd.DataFrame, estudiantes: pd.DataFrame,
    actividades_huerfanas: pd.DataFrame, sesiones_huerfanas: pd.DataFrame,
    codigos_sin_cobertura: int,
) -> ReporteCalidad:
    estudiantes_huerfanos = validar_estudiantes(hechos_validados, estudiantes)
    notas_fuera_de_rango = validar_rango_notas(hechos_validados)
    duplicados = detectar_duplicados(hechos_validados)

    filas_problematicas = (
        hechos_validados["_SESION_HUERFANA"]
        | hechos_validados["CLAVE_UNICA_ESTUDIANTE"].isin(estudiantes_huerfanos["CLAVE_UNICA_ESTUDIANTE"])
        | ~hechos_validados["NOTA_CUANTITATIVA"].between(NOTA_MIN, NOTA_MAX)
        | hechos_validados.duplicated(subset=["UID_SESION", "CLAVE_UNICA_ESTUDIANTE", "UID_ACTIVIDAD"], keep=False)
    )
    total = len(hechos_validados)
    return ReporteCalidad(
        total_filas=total,
        filas_validas=total - int(filas_problematicas.sum()),
        actividades_huerfanas=actividades_huerfanas,
        sesiones_huerfanas=sesiones_huerfanas,
        estudiantes_huerfanos=estudiantes_huerfanos,
        notas_fuera_de_rango=notas_fuera_de_rango,
        duplicados_exactos=duplicados,
        codigos_sin_cobertura=codigos_sin_cobertura,
    )


# --------------------------------------------------------------------------- #
# Análisis de asistencia (LOG_ASISTENCIA)
# --------------------------------------------------------------------------- #
def tasa_asistencia_por_sesion(log_asistencia: pd.DataFrame) -> pd.DataFrame:
    return (
        log_asistencia.groupby("UID_SESION")["ASISTENCIA_BOOL"]
        .agg(TASA_ASISTENCIA="mean", INSCRITOS_REGISTRADOS="count")
        .reset_index()
        .sort_values("TASA_ASISTENCIA")
    )


def tasa_asistencia_por_estudiante(log_asistencia: pd.DataFrame) -> pd.DataFrame:
    return (
        log_asistencia.groupby("CLAVE_UNICA_ESTUDIANTE")["ASISTENCIA_BOOL"]
        .mean()
        .rename("TASA_ASISTENCIA")
        .reset_index()
    )


def filtrar_estudiantes_en_riesgo(tasas_estudiante: pd.DataFrame) -> pd.DataFrame:
    """Estudiantes cuya RIESGO (ver `clasificar_riesgo_academico`) no es 'Bajo'.

    Única definición de "en riesgo" del proyecto -- antes coexistía con un
    segundo criterio binario (tasa < 60%) que producía un conteo distinto
    para la misma pregunta. Dos definiciones de una misma métrica en el
    mismo sistema auditado es, por definición, no trazable.
    """
    return tasas_estudiante.loc[tasas_estudiante["RIESGO"] != "Bajo"].sort_values("TASA_ASISTENCIA")


def clasificar_riesgo_academico(tasas_estudiante: pd.DataFrame) -> pd.DataFrame:
    """Clasifica cada estudiante en 3 bandas de riesgo por asistencia.

    Bandas fijas (no percentiles, mismo criterio que el motor DRM):
    < 0.40 Crítico, [0.40, 0.70) Moderado, >= 0.70 Bajo. Antes vivía
    duplicada en un script de visualización aislado del pipeline
    auditado; documentarla aquí es lo que la hace trazable en
    quality_report.md y reproducible en cualquier corrida futura.

    Requiere MODALIDAD (ver `anexar_modalidad`): sin ese desglose, esta
    clasificación por sí sola sobrestima el riesgo real, dado que virtual
    y presencial no miden asistencia con el mismo mecanismo.
    """
    condiciones = [
        tasas_estudiante["TASA_ASISTENCIA"] < LIMITE_RIESGO_CRITICO,
        tasas_estudiante["TASA_ASISTENCIA"] < LIMITE_RIESGO_MODERADO,
    ]
    tasas_estudiante = tasas_estudiante.copy()
    tasas_estudiante["RIESGO"] = np.select(condiciones, ["Crítico", "Moderado"], default="Bajo")
    return tasas_estudiante


def construir_reporte_correlacion(tasas_estudiante: pd.DataFrame, hechos: pd.DataFrame) -> pd.DataFrame:
    """Cruza tasa de asistencia (+ MODALIDAD + RIESGO) con nota promedio por
    estudiante. Única fuente para cualquier análisis o gráfico de asistencia
    vs. desempeño -- ningún script de reporte debe recalcular este cruce por
    su cuenta a partir de LOG_TRANSACCIONAL_FEEDBACK.csv."""
    promedio_notas = hechos.groupby("CLAVE_UNICA_ESTUDIANTE")["NOTA_CUANTITATIVA"].mean().rename("NOTA_PROMEDIO")
    return tasas_estudiante.merge(promedio_notas, on="CLAVE_UNICA_ESTUDIANTE", how="inner")


def correlacion_pearson(reporte_correlacion: pd.DataFrame) -> float:
    return float(reporte_correlacion["TASA_ASISTENCIA"].corr(reporte_correlacion["NOTA_PROMEDIO"]))


def ranking_participacion_sesiones(
    tasas_sesion: pd.DataFrame, n: int = 5, minimo_inscritos: int = 15,
) -> pd.DataFrame:
    """Concatena las `n` sesiones de mayor y menor participación.

    Excluye sesiones con menos de `minimo_inscritos` (grupos de 2-9
    estudiantes alcanzan 100% o 0% con una sola inasistencia, y dominarían
    ambos extremos del ranking por tamaño de muestra, no por participación
    real). El corte se documenta aquí, en el cálculo, para que cualquier
    consumidor del CSV -- no solo el gráfico -- herede el mismo criterio.
    """
    elegibles = tasas_sesion.loc[tasas_sesion["INSCRITOS_REGISTRADOS"] >= minimo_inscritos]
    menor = elegibles.nsmallest(n, "TASA_ASISTENCIA").assign(RANKING="MENOR_PARTICIPACION")
    mayor = elegibles.nlargest(n, "TASA_ASISTENCIA").assign(RANKING="MAYOR_PARTICIPACION")
    return pd.concat([mayor, menor], ignore_index=True)


def anexar_modalidad(tasas_estudiante: pd.DataFrame, estudiantes: pd.DataFrame) -> pd.DataFrame:
    """Añade MODALIDAD a un reporte de asistencia por estudiante.

    Necesario para interpretar correctamente la tasa: virtual y presencial
    no miden 'asistencia' con el mismo mecanismo (ver README), y una tasa
    agregada sin este desglose puede sobrestimar el riesgo real."""
    return tasas_estudiante.merge(estudiantes[["CLAVE_UNICA", "MODALIDAD"]],
                                   left_on="CLAVE_UNICA_ESTUDIANTE", right_on="CLAVE_UNICA", how="left") \
                            .drop(columns="CLAVE_UNICA")


# --------------------------------------------------------------------------- #
# I/O
# --------------------------------------------------------------------------- #
def _leer_csv(ruta: Path, **kwargs: object) -> pd.DataFrame:
    try:
        return pd.read_csv(ruta, **kwargs)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"No se encontró '{ruta}'.") from exc


# --------------------------------------------------------------------------- #
# Orquestación
# --------------------------------------------------------------------------- #
def ejecutar_pipeline() -> pd.DataFrame:
    DIR_SALIDA.mkdir(exist_ok=True)

    log.info("Ingesta y limpieza...")
    virtual = cargar_matriz_calificaciones(DIR_STAGING / "CALIFICACIONES_VIRTUAL.csv")
    presencial = cargar_matriz_calificaciones(DIR_STAGING / "CALIFICACIONES_PRESENCIAL.csv")
    actividades = _leer_csv(DIR_CORE / "ACTIVIDADES.csv", dtype={"NUM_SESION": str})
    sesiones = _leer_csv(DIR_CORE / "REGISTRO_SESIONES.csv")
    estudiantes = _leer_csv(DIR_CORE / "REGISTRO_ESTUDIANTES.csv")
    diccionario = _leer_csv(DIR_CORE / "DICCIONARIO_FEEDBACK.csv")

    log.info("Transformación: unpivot...")
    largo = pd.concat([
        unpivotar_matriz(virtual, "V", MAPA_VIRTUAL),
        unpivotar_matriz(presencial, "P", MAPA_PRESENCIAL),
    ], ignore_index=True)

    log.info("Enriquecimiento: Merge 1 (ACTIVIDADES)...")
    largo, actividades_huerfanas = enriquecer_con_actividades(largo, actividades)
    if not actividades_huerfanas.empty:
        log.warning("%d combinaciones sin actividad en el catálogo (excluidas).", len(actividades_huerfanas))

    log.info("Enriquecimiento: Merge 2 (REGISTRO_SESIONES)...")
    largo, sesiones_huerfanas = enriquecer_con_sesiones(largo, sesiones)
    if not sesiones_huerfanas.empty:
        log.warning("%d combinaciones grupo+sesión sin fila en REGISTRO_SESIONES (UID_SESION de respaldo).",
                    len(sesiones_huerfanas))

    log.info("Normalización matemática: IMPACTO_REAL...")
    largo = calcular_impacto_real(largo)

    log.info("Motor de estimación DRM...")
    largo = aplicar_motor_estimacion(largo, diccionario)
    codigos_sin_cobertura = int((largo["COD_FEEDBACK_ESTIMADO"] == SIN_CODIGO).sum())

    log.info("Validaciones de calidad...")
    reporte = construir_reporte_calidad(largo, estudiantes, actividades_huerfanas, sesiones_huerfanas, codigos_sin_cobertura)
    (DIR_SALIDA / "quality_report.md").write_text(reporte.render_markdown(), encoding="utf-8")
    log.info("Registros válidos: %.1f%%", reporte.porcentaje_valido)

    log.info("Carga: exportando LOG_TRANSACCIONAL_FEEDBACK.csv...")
    largo["COD_FEEDBACK"] = pd.NA
    hechos_final = largo[COLUMNAS_SALIDA]
    hechos_final.to_csv(DIR_SALIDA / "LOG_TRANSACCIONAL_FEEDBACK.csv", index=False)
    log.info("Listo -> %s (%d filas)", DIR_SALIDA / "LOG_TRANSACCIONAL_FEEDBACK.csv", len(hechos_final))

    ruta_asistencia = DIR_LOGS / "LOG_ASISTENCIA.csv"
    if ruta_asistencia.exists():
        log.info("Analítica de asistencia...")
        log_asistencia = _leer_csv(ruta_asistencia)
        tasas_sesion = tasa_asistencia_por_sesion(log_asistencia)
        tasas_estudiante = anexar_modalidad(tasa_asistencia_por_estudiante(log_asistencia), estudiantes)
        tasas_estudiante = clasificar_riesgo_academico(tasas_estudiante)
        riesgo = filtrar_estudiantes_en_riesgo(tasas_estudiante)
        reporte_correlacion = construir_reporte_correlacion(tasas_estudiante, hechos_final)
        correlacion = correlacion_pearson(reporte_correlacion)
        ranking = ranking_participacion_sesiones(tasas_sesion)
        ranking_15 = ranking_participacion_sesiones(tasas_sesion, n=15)

        tasas_sesion.to_csv(DIR_SALIDA / "tasa_asistencia_sesion.csv", index=False)
        tasas_estudiante.to_csv(DIR_SALIDA / "tasa_asistencia_estudiante.csv", index=False)
        riesgo.to_csv(DIR_SALIDA / "estudiantes_riesgo.csv", index=False)
        reporte_correlacion.to_csv(DIR_SALIDA / "correlacion_asistencia_desempeno.csv", index=False)
        ranking.to_csv(DIR_SALIDA / "ranking_sesiones.csv", index=False)
        ranking_15.to_csv(DIR_SALIDA / "ranking_sesiones_top15.csv", index=False)

        log.info("Asistencia promedio -- Virtual: %.1f%% | Presencial: %.1f%%",
                  100 * tasas_estudiante.loc[tasas_estudiante.MODALIDAD == "V", "TASA_ASISTENCIA"].mean(),
                  100 * tasas_estudiante.loc[tasas_estudiante.MODALIDAD == "P", "TASA_ASISTENCIA"].mean())
        log.info("Clasificación de riesgo: %s (en riesgo: %d de %d)",
                  tasas_estudiante["RIESGO"].value_counts().to_dict(), len(riesgo), len(tasas_estudiante))
        log.info("Correlación asistencia-desempeño (Pearson): %.3f", correlacion)

    return hechos_final


def main() -> None:
    try:
        hechos = ejecutar_pipeline()
    except (FileNotFoundError, ValueError) as exc:
        log.error("El pipeline se detuvo: %s", exc)
        raise SystemExit(1) from exc

    total = len(hechos)
    excelente = int((hechos["COD_FEEDBACK_ESTIMADO"] == "GEN_OK").sum())
    log.info("Resumen: %d filas | GEN_OK: %d (%.1f%%)", total, excelente, 100 * excelente / total)


if __name__ == "__main__":
    main()
