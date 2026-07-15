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


def get_sesiones_activas_por_camara(usuario_id: int, camara_id: int) -> list[tuple]:
    """Sesiones 'activo' de camara_ip para esta cámara+usuario (debería ser 0 o 1)."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {_COLS} FROM sesiones_monitoreo
                WHERE usuario_id = %s AND camara_id = %s
                  AND tipo_fuente = 'camara_ip' AND estado = 'activo'
                """,
                (usuario_id, camara_id),
            )
            return cur.fetchall()


def get_cualquier_sesion_activa_por_camara(camara_id: int) -> tuple | None:
    """
    Sesión 'activo' de camara_ip para esta cámara, sin filtrar por usuario.
    Se usa como fallback cuando una petición pierde la carrera contra el
    índice único (otra petición concurrente, tal vez de otro usuario, ya
    dejó activa una sesión para esta cámara) — en vez de fallar, se devuelve
    la que ganó.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {_COLS} FROM sesiones_monitoreo
                WHERE camara_id = %s AND tipo_fuente = 'camara_ip' AND estado = 'activo'
                """,
                (camara_id,),
            )
            return cur.fetchone()


def detener_todas_las_sesiones_activas() -> int:
    """
    Marca como 'detenido' TODAS las sesiones que quedaron en 'activo'.
    Se llama al arrancar la app: un proceso recién iniciado no puede tener
    ningún hilo en background vivo todavía, así que cualquier sesión 'activo'
    en la BD a esta altura es basura de un cierre anterior (crash, Ctrl+C,
    reinicio) que nunca se cerró correctamente.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE sesiones_monitoreo
                SET estado = 'detenido', fecha_fin = NOW()
                WHERE estado = 'activo'
                """
            )
            return cur.rowcount
