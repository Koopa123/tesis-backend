from app.database import get_db

_COLS = (
    "e.camara_id, e.zona_config_id, e.personas, e.nivel, e.alerta_activa, "
    "e.frame_evidencia_b64, e.fecha_actualizacion, c.nombre, c.ubicacion"
)


def upsert_estado(
    camara_id: int,
    zona_config_id: int | None,
    personas: int,
    nivel: str,
    alerta_activa: bool,
    frame_evidencia_b64: str | None = None,
) -> None:
    """Guarda el último estado reportado por la laptop del local para una cámara."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO estado_camaras_edge
                    (camara_id, zona_config_id, personas, nivel, alerta_activa,
                     frame_evidencia_b64, fecha_actualizacion)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (camara_id) DO UPDATE SET
                    zona_config_id      = EXCLUDED.zona_config_id,
                    personas            = EXCLUDED.personas,
                    nivel               = EXCLUDED.nivel,
                    alerta_activa       = EXCLUDED.alerta_activa,
                    -- solo se sobrescribe la evidencia si vino una nueva
                    frame_evidencia_b64 = COALESCE(EXCLUDED.frame_evidencia_b64,
                                                    estado_camaras_edge.frame_evidencia_b64),
                    fecha_actualizacion = NOW()
                """,
                (camara_id, zona_config_id, personas, nivel, alerta_activa, frame_evidencia_b64),
            )


def list_estados() -> list[tuple]:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {_COLS}
                FROM estado_camaras_edge e
                JOIN camaras_ip c ON c.id = e.camara_id
                ORDER BY c.nombre
                """
            )
            return cur.fetchall()
