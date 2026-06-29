-- =============================================================
-- Esquema inicial para el backend de detección de aglomeraciones
-- Compatible con Supabase PostgreSQL
-- Ejecutar en: Supabase → SQL Editor → New query
-- =============================================================

-- ── Tabla de usuarios ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS usuarios (
    id              SERIAL PRIMARY KEY,
    nombre          VARCHAR(100)  NOT NULL,
    email           VARCHAR(255)  NOT NULL UNIQUE,
    password_hash   TEXT          NOT NULL,
    rol             VARCHAR(20)   NOT NULL DEFAULT 'vigilante'
                        CHECK (rol IN ('vigilante', 'administrador')),
    activo          BOOLEAN       NOT NULL DEFAULT TRUE,
    fecha_creacion  TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Índice para búsquedas por email (login)
CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_email ON usuarios (email);

-- ── Tabla de presets ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS presets (
    id              SERIAL PRIMARY KEY,
    nombre          VARCHAR(100)  NOT NULL,
    frame_path      TEXT          NOT NULL,
    zonas           JSONB         NOT NULL DEFAULT '[]',
    fecha_creacion  TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ── Tabla de análisis ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS analisis (
    id                  SERIAL PRIMARY KEY,
    nombre_video        TEXT          NOT NULL,
    personas_maximas    INTEGER       NOT NULL DEFAULT 0,
    grupo_mayor_maximo  INTEGER       NOT NULL DEFAULT 0,
    nivel_final         VARCHAR(10)   NOT NULL DEFAULT 'BAJO'
                            CHECK (nivel_final IN ('BAJO', 'MEDIO', 'ALTO')),
    preset_id           INTEGER       REFERENCES presets (id) ON DELETE SET NULL,
    fecha               TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Índice para historial ordenado por fecha
CREATE INDEX IF NOT EXISTS idx_analisis_fecha ON analisis (fecha DESC);
