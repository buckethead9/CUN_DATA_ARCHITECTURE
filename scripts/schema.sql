-- =============================================================================
-- Ledger Docente CUN 2026 -- Star Schema DDL
-- =============================================================================
-- Capas:
--   STAGING     CALIFICACIONES_VIRTUAL, CALIFICACIONES_PRESENCIAL
--               Matrices anchas, no normalizadas. Insumo crudo del ETL;
--               no se consultan directamente en el modelo analítico.
--   DIMENSION   REGISTRO_ESTUDIANTES, REGISTRO_SESIONES, ACTIVIDADES,
--               DICCIONARIO_FEEDBACK
--   HECHOS      LOG_TRANSACCIONAL_FEEDBACK (grano: estudiante x actividad),
--               LOG_ASISTENCIA (grano: estudiante x sesión)
-- Dialecto: SQL estándar / PostgreSQL. Ajustar BIGSERIAL -> AUTOINCREMENT o
-- IDENTITY según el motor de destino.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- DIMENSIÓN: ESTUDIANTES
-- -----------------------------------------------------------------------------
CREATE TABLE REGISTRO_ESTUDIANTES (
    CLAVE_UNICA        VARCHAR(30)   NOT NULL,
    ID_ESTUDIANTE      VARCHAR(20)   NOT NULL,
    NOMBRE             VARCHAR(150)  NOT NULL,
    EMAIL              VARCHAR(150),
    MATERIA            VARCHAR(20)   NOT NULL,
    MODALIDAD          CHAR(1)       NOT NULL,
    GRUPO              VARCHAR(10)   NOT NULL,
    GRUPO_PROYECTO     VARCHAR(30),
    CONSTRAINT PK_REGISTRO_ESTUDIANTES PRIMARY KEY (CLAVE_UNICA),
    CONSTRAINT CK_ESTUDIANTES_MODALIDAD CHECK (MODALIDAD IN ('V', 'P'))
);

-- -----------------------------------------------------------------------------
-- DIMENSIÓN: SESIONES
-- -----------------------------------------------------------------------------
CREATE TABLE REGISTRO_SESIONES (
    UID_SESION         VARCHAR(30)   NOT NULL,
    TIMESTAMP_INICIO   TIMESTAMP,
    TIMESTAMP_FIN      TIMESTAMP,
    MATERIA            VARCHAR(20)   NOT NULL,
    GRUPO              VARCHAR(10)   NOT NULL,
    UID_GRUPO          VARCHAR(20)   NOT NULL,
    SESION             INTEGER       NOT NULL,
    ASISTENTES         INTEGER,
    INSCRITOS          INTEGER,
    LATENCIA_MIN       NUMERIC(6,2),
    ICE_INDICE         NUMERIC(6,4),
    BIT_DRM            BOOLEAN,
    CONSTRAINT PK_REGISTRO_SESIONES PRIMARY KEY (UID_SESION),
    CONSTRAINT CK_SESIONES_CONTEO CHECK (ASISTENTES IS NULL OR ASISTENTES <= INSCRITOS)
);

-- -----------------------------------------------------------------------------
-- DIMENSIÓN: CATÁLOGO DE ACTIVIDADES
-- -----------------------------------------------------------------------------
CREATE TABLE ACTIVIDADES (
    UID_ACTIVIDAD      VARCHAR(30)   NOT NULL,
    MATERIA            VARCHAR(20)   NOT NULL,
    MODALIDAD          CHAR(1)       NOT NULL,
    ACTIVIDAD          VARCHAR(30)   NOT NULL,
    HITO               VARCHAR(5)    NOT NULL,
    CORTE              VARCHAR(5)    NOT NULL,
    PESO               NUMERIC(4,3)  NOT NULL,
    NUM_SESION         VARCHAR(5)    NOT NULL,
    CONSTRAINT PK_ACTIVIDADES PRIMARY KEY (UID_ACTIVIDAD),
    CONSTRAINT UQ_ACTIVIDADES_NATURAL UNIQUE (MATERIA, MODALIDAD, ACTIVIDAD),
    CONSTRAINT CK_ACTIVIDADES_MODALIDAD CHECK (MODALIDAD IN ('V', 'P')),
    CONSTRAINT CK_ACTIVIDADES_PESO CHECK (PESO BETWEEN 0 AND 1)
);
-- UQ_ACTIVIDADES_NATURAL es la llave que usa el ETL para el Merge 1
-- (join contra MATERIA + MODALIDAD + ACTIVIDAD, nunca por concatenación de texto).

-- -----------------------------------------------------------------------------
-- DIMENSIÓN: DICCIONARIO DE AUDITORÍA
-- -----------------------------------------------------------------------------
CREATE TABLE DICCIONARIO_FEEDBACK (
    COD_FEEDBACK       VARCHAR(20)   NOT NULL,
    CONCEPTO           VARCHAR(50)   NOT NULL,
    TIPO_ERROR         VARCHAR(20)   NOT NULL,
    COEF_IMPACTO       NUMERIC(3,2)  NOT NULL,
    MATERIA            VARCHAR(20)   NOT NULL,
    MENSAJE            TEXT          NOT NULL,
    CONSTRAINT PK_DICCIONARIO_FEEDBACK PRIMARY KEY (COD_FEEDBACK),
    CONSTRAINT CK_DICCIONARIO_COEFICIENTE CHECK (COEF_IMPACTO BETWEEN 0 AND 1)
);

-- -----------------------------------------------------------------------------
-- STAGING: MATRICES ANCHAS (insumo crudo -- se descartan tras el ETL)
-- -----------------------------------------------------------------------------
CREATE TABLE CALIFICACIONES_VIRTUAL (
    UID_GRUPO          VARCHAR(20)   NOT NULL,
    ID_ESTUDIANTE      VARCHAR(20)   NOT NULL,
    NOMBRE             VARCHAR(150),
    GRUPO_PROYECTO     VARCHAR(30),
    QUIZ_1             NUMERIC(3,2),
    PARCIAL_1          NUMERIC(3,2),
    CORTE_1            NUMERIC(3,2),
    PARCIAL_2          NUMERIC(3,2),
    QUIZ_2             NUMERIC(3,2),
    CORTE_2            NUMERIC(3,2),
    QUIZ_3             NUMERIC(3,2),
    AUTOEVALUACION     NUMERIC(3,2),
    COEVALUACION       NUMERIC(3,2),
    ACA_FINAL          NUMERIC(3,2),
    NOTA_FINAL         NUMERIC(3,2),
    CONSTRAINT PK_CALIF_VIRTUAL PRIMARY KEY (UID_GRUPO, ID_ESTUDIANTE)
);

CREATE TABLE CALIFICACIONES_PRESENCIAL (
    UID_GRUPO          VARCHAR(20)   NOT NULL,
    ID_ESTUDIANTE      VARCHAR(20)   NOT NULL,
    NOMBRE             VARCHAR(150),
    GRUPO_PROYECTO     VARCHAR(30),
    QUIZ_1             NUMERIC(3,2),
    IDEA               NUMERIC(3,2),
    PARCIAL_1          NUMERIC(3,2),
    CORTE_1            NUMERIC(3,2),
    DEBATE             NUMERIC(3,2),
    PROY_DES           NUMERIC(3,2),
    PITCH              NUMERIC(3,2),
    CORTE_2            NUMERIC(3,2),
    QUIZ_2             NUMERIC(3,2),
    AUTOEVALUACION     NUMERIC(3,2),
    COEVALUACION       NUMERIC(3,2),
    ACA_FINAL          NUMERIC(3,2),
    NOTA_FINAL         NUMERIC(3,2),
    CONSTRAINT PK_CALIF_PRESENCIAL PRIMARY KEY (UID_GRUPO, ID_ESTUDIANTE)
);

-- -----------------------------------------------------------------------------
-- HECHOS: ASISTENCIA (grano: 1 fila = 1 estudiante x 1 sesión)
-- -----------------------------------------------------------------------------
CREATE TABLE LOG_ASISTENCIA (
    ID                       BIGSERIAL     NOT NULL,
    FECHA                    DATE          NOT NULL,
    UID_SESION               VARCHAR(30)   NOT NULL,
    CLAVE_UNICA_ESTUDIANTE   VARCHAR(30)   NOT NULL,
    NOMBRE                   VARCHAR(150),
    UID_GRUPO                VARCHAR(20)   NOT NULL,
    ASISTENCIA_BOOL          BOOLEAN       NOT NULL,
    ORIGEN_DATO              VARCHAR(30),
    CONSTRAINT PK_LOG_ASISTENCIA PRIMARY KEY (ID),
    CONSTRAINT UQ_ASISTENCIA_NATURAL UNIQUE (UID_SESION, CLAVE_UNICA_ESTUDIANTE),
    CONSTRAINT FK_ASISTENCIA_SESION FOREIGN KEY (UID_SESION)
        REFERENCES REGISTRO_SESIONES (UID_SESION),
    CONSTRAINT FK_ASISTENCIA_ESTUDIANTE FOREIGN KEY (CLAVE_UNICA_ESTUDIANTE)
        REFERENCES REGISTRO_ESTUDIANTES (CLAVE_UNICA)
);

-- -----------------------------------------------------------------------------
-- HECHOS: FEEDBACK TRANSACCIONAL (grano: 1 fila = 1 estudiante x 1 actividad)
-- Tabla de destino del motor ETL (main.py).
-- -----------------------------------------------------------------------------
CREATE TABLE LOG_TRANSACCIONAL_FEEDBACK (
    ID                       BIGSERIAL      NOT NULL,
    UID_SESION               VARCHAR(30)    NOT NULL,
    CLAVE_UNICA_ESTUDIANTE   VARCHAR(30)    NOT NULL,
    UID_ACTIVIDAD            VARCHAR(30)    NOT NULL,
    NOTA_CUANTITATIVA        NUMERIC(3,2)   NOT NULL,
    IMPACTO_REAL             NUMERIC(6,4)   NOT NULL,      -- NOTA_CUANTITATIVA * ACTIVIDADES.PESO
    COD_FEEDBACK             VARCHAR(20),                  -- definitivo; lo asigna el docente
    COD_FEEDBACK_ESTIMADO    VARCHAR(150),                 -- candidatos separados por '|'; no es FK simple
    CONSTRAINT PK_LOG_TRANSACCIONAL_FEEDBACK PRIMARY KEY (ID),
    CONSTRAINT UQ_FEEDBACK_NATURAL UNIQUE (UID_SESION, CLAVE_UNICA_ESTUDIANTE, UID_ACTIVIDAD),
    CONSTRAINT CK_FEEDBACK_NOTA CHECK (NOTA_CUANTITATIVA BETWEEN 0 AND 5),
    CONSTRAINT FK_FEEDBACK_SESION FOREIGN KEY (UID_SESION)
        REFERENCES REGISTRO_SESIONES (UID_SESION),
    CONSTRAINT FK_FEEDBACK_ESTUDIANTE FOREIGN KEY (CLAVE_UNICA_ESTUDIANTE)
        REFERENCES REGISTRO_ESTUDIANTES (CLAVE_UNICA),
    CONSTRAINT FK_FEEDBACK_ACTIVIDAD FOREIGN KEY (UID_ACTIVIDAD)
        REFERENCES ACTIVIDADES (UID_ACTIVIDAD),
    CONSTRAINT FK_FEEDBACK_COD FOREIGN KEY (COD_FEEDBACK)
        REFERENCES DICCIONARIO_FEEDBACK (COD_FEEDBACK)
);
-- COD_FEEDBACK_ESTIMADO no lleva FK: puede contener 0, 1 o varios códigos
-- concatenados ("IO_OBJ|IO_PITCH"), es una lista de candidatos calculada por
-- el motor de estimación, no un valor atómico referenciable.

-- -----------------------------------------------------------------------------
-- ÍNDICES (columnas FK más consultadas en el modelo de hechos)
-- -----------------------------------------------------------------------------
CREATE INDEX IX_FEEDBACK_ESTUDIANTE ON LOG_TRANSACCIONAL_FEEDBACK (CLAVE_UNICA_ESTUDIANTE);
CREATE INDEX IX_FEEDBACK_ACTIVIDAD  ON LOG_TRANSACCIONAL_FEEDBACK (UID_ACTIVIDAD);
CREATE INDEX IX_FEEDBACK_SESION     ON LOG_TRANSACCIONAL_FEEDBACK (UID_SESION);
CREATE INDEX IX_ASISTENCIA_ESTUDIANTE ON LOG_ASISTENCIA (CLAVE_UNICA_ESTUDIANTE);
CREATE INDEX IX_ASISTENCIA_SESION     ON LOG_ASISTENCIA (UID_SESION);
CREATE INDEX IX_ACTIVIDADES_MATERIA   ON ACTIVIDADES (MATERIA, MODALIDAD);
CREATE INDEX IX_DICCIONARIO_MATERIA   ON DICCIONARIO_FEEDBACK (MATERIA, COEF_IMPACTO);
