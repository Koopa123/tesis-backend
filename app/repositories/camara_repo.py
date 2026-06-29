from app.database import get_db

_COLS = "id, nombre, direccion_ip, ubicacion, descripcion, activa, fecha_registro"


def create_camara(
    nombre: str,
    direccion_ip: str,
    ubicacion: str,
    descripcion: str | None,
    activa: bool,
) -> tuple:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO camaras_ip (nombre, direccion_ip, ubicacion, descripcion, activa)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING {_COLS}
                """,
                (nombre, direccion_ip, ubicacion, descripcion, activa),
            )
            return cur.fetchone()


def list_camaras(solo_activas: bool = False) -> list[tuple]:
    with get_db() as conn:
        with conn.cursor() as cur:
            query = f"SELECT {_COLS} FROM camaras_ip"
            if solo_activas:
                query += " WHERE activa = TRUE"
            query += " ORDER BY id"
            cur.execute(query)
            return cur.fetchall()


def get_camara(camara_id: int) -> tuple | None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT {_COLS} FROM camaras_ip WHERE id = %s",
                (camara_id,),
            )
            return cur.fetchone()


def update_estado(camara_id: int, activa: bool) -> tuple | None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE camaras_ip SET activa = %s
                WHERE id = %s
                RETURNING {_COLS}
                """,
                (activa, camara_id),
            )
            return cur.fetchone()


def delete_camara(camara_id: int) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM camaras_ip WHERE id = %s", (camara_id,))
