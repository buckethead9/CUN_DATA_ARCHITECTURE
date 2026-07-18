# Reporte de Calidad de Datos

Generado: 2026-07-18 14:08

## Resumen

- Total de filas procesadas: **5476**
- Registros válidos: **5256** (96.0%)
- Filas sin código de auditoría estimable: **64**

## Actividades sin correspondencia en ACTIVIDADES

Ninguna. Todas las columnas de las matrices de origen resolvieron a un UID_ACTIVIDAD.

## Sesiones huérfanas (UID_SESION sin fila en REGISTRO_SESIONES)

10 encontrados.

| UID_GRUPO      |   NUM_SESION | UID_ACTIVIDAD     |
|:---------------|-------------:|:------------------|
| IO_ADMIN_30101 |            2 | IO_ADMIN_Q1_H1    |
| IO_ADMIN_30101 |            4 | IO_ADMIN_IDEA_H1  |
| IO_ADMIN_30101 |            3 | IO_ADMIN_P1_H1    |
| IO_ADMIN_30101 |            6 | IO_ADMIN_DEB_H2   |
| IO_ADMIN_30101 |            7 | IO_ADMIN_PROY_H3  |
| IO_ADMIN_30101 |            8 | IO_ADMIN_PITCH_H3 |
| IO_ADMIN_30101 |           11 | IO_ADMIN_Q2_H1    |
| IO_ADMIN_30101 |           11 | IO_ADMIN_AUTO_H1  |
| IO_ADMIN_30101 |           11 | IO_ADMIN_COE_H1   |
| IO_ADMIN_30101 |           10 | IO_ADMIN_FINAL_H4 |

## Estudiantes inexistentes (CLAVE_UNICA_ESTUDIANTE sin fila en REGISTRO_ESTUDIANTES)

Ninguno. Todo estudiante en las calificaciones está en el maestro.

## Notas fuera de rango [0.0, 5.0]

Ninguna. Todas las notas están dentro de la escala.

## Duplicados exactos

Ninguno.
