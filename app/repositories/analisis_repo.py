from app.database import get_db


def save_analisis(
    nombre_video: str,
    personas_maximas: int,
    grupo_mayor_maximo: int,
    nivel_final: str,
    preset_id: int | None = None,
) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO analisis
                    (nombre_video, personas_maximas, grupo_mayor_maximo, nivel_final, preset_id)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (nombre_video, personas_maximas, grupo_mayor_maximo, nivel_final, preset_id),
            )


def list_analisis() -> list[tuple]:
    """
    Retorna filas: (id, nombre_video, personas_maximas, grupo_mayor_maximo,
                    nivel_final, fecha, preset_nombre)
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    a.id, a.nombre_video, a.personas_maximas,
                    a.grupo_mayor_maximo, a.nivel_final, a.fecha,
                    p.nombre AS preset_nombre
                FROM analisis a
                LEFT JOIN presets p ON a.preset_id = p.id
                ORDER BY a.fecha DESC
                """
            )
            return cur.fetchall()
