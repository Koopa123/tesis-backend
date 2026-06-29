from app.database import get_db

_COLS = (
    "id, usuario_id, tipo_fuente, camara_id, grabacion_id, "
    "zona_exclusion_id, estado, fecha_inicio, fecha_fin"
)


def create_sesion(
    usuario_id: int,
    tipo_fuente: str,
    camara_id: int | None = None,
    grabacion_id: int | None = None,
    zona_exclusion_id: int | None = None,
) -> tuple:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO sesiones_monitoreo
                    (usuario_id, tipo_fuente, camara_id, grabacion_id, zona_exclusion_id, estado)
                VALUES (%s, %s, %s, %s, %s, 'activo')
                RETURNING {_COLS}
                """,
                (usuario_id, tipo_fuente, camara_id, grabacion_id, zona_exclusion_id),
            )
            return cur.fetchone()


def get_sesion(sesion_id: int) -> tuple | None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT {_COLS} FROM sesiones_monitoreo WHERE id = %s",
                (sesion_id,),
            )
            return cur.fetchone()


def detener_sesion(sesion_id: int) -> tuple:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE sesiones_monitoreo
                SET estado = 'detenido', fecha_fin = NOW()
                WHERE id = %s
                RETURNING {_COLS}
                """,
                (sesion_id,),
            )
            return cur.fetchone()
