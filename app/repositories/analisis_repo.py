from app.database import get_db

_COLS = (
    "id, sesion_id, zona_config_id, personas_maximas, nivel_maximo, "
    "tiempo_primera_media_seg, alerta_activada, frames_procesados, "
    "inicio_analisis, fin_analisis, fecha_registro"
)


def save_resultado(
    sesion_id: int,
    zona_config_id: int | None,
    personas_maximas: int,
    nivel_maximo: str,
    tiempo_primera_media_seg: float | None,
    alerta_activada: bool,
    frames_procesados: int,
    inicio_analisis: str | None = None,
    fin_analisis: str | None = None,
) -> tuple:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO resultados_analisis
                    (sesion_id, zona_config_id, personas_maximas, nivel_maximo,
                     tiempo_primera_media_seg, alerta_activada, frames_procesados,
                     inicio_analisis, fin_analisis)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING {_COLS}
                """,
                (sesion_id, zona_config_id, personas_maximas, nivel_maximo,
                 tiempo_primera_media_seg, alerta_activada, frames_procesados,
                 inicio_analisis, fin_analisis),
            )
            return cur.fetchone()


def get_resultado_by_sesion(sesion_id: int) -> tuple | None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {_COLS} FROM resultados_analisis
                WHERE sesion_id = %s
                ORDER BY fecha_registro DESC
                LIMIT 1
                """,
                (sesion_id,),
            )
            return cur.fetchone()


def list_resultados(usuario_id: int | None = None) -> list[tuple]:
    """Admin ve todo; vigilante ve solo sus sesiones."""
    with get_db() as conn:
        with conn.cursor() as cur:
            if usuario_id is None:
                cur.execute(
                    f"""
                    SELECT {_COLS} FROM resultados_analisis
                    ORDER BY fecha_registro DESC
                    LIMIT 100
                    """
                )
            else:
                cur.execute(
                    f"""
                    SELECT r.{', r.'.join(_COLS.split(', '))}
                    FROM resultados_analisis r
                    JOIN sesiones_monitoreo s ON s.id = r.sesion_id
                    WHERE s.usuario_id = %s
                    ORDER BY r.fecha_registro DESC
                    LIMIT 100
                    """,
                    (usuario_id,),
                )
            return cur.fetchall()
