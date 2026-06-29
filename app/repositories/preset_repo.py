import json

from app.database import get_db


def create_preset(nombre: str, frame_path: str, zonas: list) -> int:
    """Crea un preset y retorna su id."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO presets (nombre, frame_path, zonas)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (nombre, frame_path, json.dumps(zonas)),
            )
            return cur.fetchone()[0]


def list_presets() -> list[tuple]:
    """Retorna todos los presets ordenados por fecha DESC."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, nombre, frame_path, zonas, fecha_creacion FROM presets ORDER BY fecha_creacion DESC"
            )
            return cur.fetchall()


def get_preset(preset_id: int) -> tuple | None:
    """Retorna (id, nombre, frame_path, zonas, fecha_creacion) o None."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, nombre, frame_path, zonas, fecha_creacion FROM presets WHERE id = %s",
                (preset_id,),
            )
            return cur.fetchone()


def update_preset_zones(preset_id: int, zonas: list) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE presets SET zonas = %s WHERE id = %s",
                (json.dumps(zonas), preset_id),
            )


def delete_preset(preset_id: int) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM presets WHERE id = %s", (preset_id,))
