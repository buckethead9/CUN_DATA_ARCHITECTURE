# CUN Data Architecture — Sistema de Trazabilidad Académica

Pipeline ETL que consolida el registro de calificaciones y asistencia de un
curso universitario (652 estudiantes, 15 grupos, 6 materias, modalidad
virtual y presencial) en un modelo relacional *star schema*, con validación
de integridad referencial y estimación auditable de códigos de feedback.

Para el razonamiento detrás de cada decisión de diseño — el modelo DRM, por
qué el motor de estimación usa bandas fijas y no percentiles, y los dos
problemas de integridad reales que este pipeline detectó — ver
[`docs/ARQUITECTURA.md`](docs/ARQUITECTURA.md).

## Estructura del proyecto

```
CUN_DATA_ARCHITECTURE/
├── main.py                  # motor ETL (punto de entrada)
├── data/
│   ├── core/                # dimensiones: REGISTRO_ESTUDIANTES, REGISTRO_SESIONES,
│   │                         # ACTIVIDADES, DICCIONARIO_FEEDBACK
│   ├── staging/              # CALIFICACIONES_VIRTUAL / PRESENCIAL (matrices anchas)
│   └── logs/                 # LOG_ASISTENCIA (hecho de entrada)
├── outputs/                  # generado por main.py (ver abajo)
├── docs/
│   └── ARQUITECTURA.md       # star schema, modelo DRM, decisiones de diseño
└── scripts/
    └── schema.sql            # DDL de las 8 tablas (PK, FK, star schema)
```

## Dependencias

```
python >= 3.12
pandas >= 2.0
tabulate                       # requerido por pandas para el quality_report.md
```

```bash
pip install pandas tabulate
```

## Ejecución

```bash
python main.py
```

`main.py` resuelve las rutas de entrada/salida relativas a su propia
ubicación (`Path(__file__).parent`), por lo que puede ejecutarse desde
cualquier directorio de trabajo.

## Salidas (`outputs/`)

| Archivo | Contenido |
|---|---|
| `LOG_TRANSACCIONAL_FEEDBACK.csv` | Tabla de hechos final: 1 fila = 1 estudiante × 1 actividad |
| `quality_report.md` | Hallazgos de integridad referencial y % de registros válidos |
| `tasa_asistencia_sesion.csv` | Tasa de participación por sesión |
| `tasa_asistencia_estudiante.csv` | Tasa de asistencia por estudiante, con `MODALIDAD` y `RIESGO` (Crítico/Moderado/Bajo) |
| `estudiantes_riesgo.csv` | Estudiantes con `RIESGO != "Bajo"` — única definición de "en riesgo" del proyecto |
| `correlacion_asistencia_desempeno.csv` | Asistencia + nota promedio por estudiante — fuente única para cualquier análisis o gráfico de esta relación |
| `ranking_sesiones.csv` / `ranking_sesiones_top15.csv` | Top / bottom N sesiones por participación (excluye sesiones con < 15 inscritos) |
| `visuals/*.png` | Gráficos de publicación — ver `scripts/generar_visuales.py` |

## Visualizaciones

```bash
python scripts/generar_visuales.py
```

Genera `outputs/visuals/*.png` leyendo **exclusivamente** de `outputs/` —
ningún gráfico recalcula una métrica que el pipeline ya produjo. Si un
número no está en un CSV de `outputs/`, no aparece en un gráfico.

## Resultado de la corrida más reciente

```
5,476 filas procesadas | 96.0% registros válidos
GEN_OK (automático): 2,733 (49.9%)
Clasificación de riesgo: Crítico 451 · Moderado 86 · Bajo 115 (537 en riesgo de 652)
Correlación asistencia-desempeño (Pearson): 0.262 global
  -- por modalidad: Presencial r=0.78 (fuerte) · Virtual r=0.29 (débil)
Asistencia promedio -- Virtual: 15.0% | Presencial: 67.8%
```

La brecha virtual/presencial en asistencia **no es necesariamente un
problema de los estudiantes** — puede reflejar que ambas modalidades no
miden "asistencia" con el mismo mecanismo. La correlación global (0.262)
también oculta que la relación es fuerte en presencial y débil en virtual —
ver `ARQUITECTURA.md` antes de sacar conclusiones sobre estudiantes en
riesgo o sobre "la asistencia no importa".
