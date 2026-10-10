import json

import psycopg2

from app.database import get_db

_COLS = (
    "id, nombre, frame_referencia, zonas, "
    "umbral_medio, umbral_alto, ventana_segundos, cooldown_segundos, "
    "creado_por, activa, fecha_creacion, fecha_actualizacion"
)


def create_zona(
    nombre: str,
    frame_referencia: str,
    zonas: list,
    creado_por: int,
    umbral_medio: int = 4,
    umbral_alto: int = 6,
    ventana_segundos: float = 2.0,
    cooldown_segundos: int = 10,
    frame_imagen: bytes | None = None,
    frame_mime: str | None = None,
) -> tuple:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO configuraciones_zonas_exclusion
                    (nombre, frame_referencia, zonas,
                     umbral_medio, umbral_alto, ventana_segundos, cooldown_segundos,
                     creado_por, frame_imagen, frame_mime)
                VALUES (%s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s)
                RETURNING {_COLS}
                """,
                (nombre, frame_referencia, json.dumps(zonas),
                 umbral_medio, umbral_alto, ventana_segundos, cooldown_segundos,
                 creado_por,
                 psycopg2.Binary(frame_imagen) if frame_imagen is not None else None,
                 frame_mime),
            )
            return cur.fetchone()


def list_zonas() -> list[tuple]:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {_COLS}
                FROM configuraciones_zonas_exclusion
                WHERE activa = TRUE
                ORDER BY fecha_creacion DESC
                """
            )
            return cur.fetchall()


def get_zona(zona_id: int) -> tuple | None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT {_COLS} FROM configuraciones_zonas_exclusion WHERE id = %s",
                (zona_id,),
            )
            return cur.fetchone()


def get_frame(frame_referencia: str) -> tuple | None:
    """(bytes, mime) de la imagen de referencia guardada en la BD, o None."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT frame_imagen, frame_mime
                FROM configuraciones_zonas_exclusion
                WHERE frame_referencia = %s AND frame_imagen IS NOT NULL
                """,
                (frame_referencia,),
            )
            return cur.fetchone()


def update_zona(
    zona_id: int,
    nombre: str | None = None,
    frame_referencia: str | None = None,
    frame_imagen: bytes | None = None,
    frame_mime: str | None = None,
    zonas: list | None = None,
    umbral_medio: int | None = None,
    umbral_alto: int | None = None,
    ventana_segundos: float | None = None,
    cooldown_segundos: int | None = None,
) -> tuple | None:
    sets = ["fecha_actualizacion = CURRENT_TIMESTAMP"]
    params: list = []

    if nombre is not None:
        sets.append("nombre = %s")
        params.append(nombre)
    if frame_referencia is not None:
        sets.append("frame_referencia = %s")
        params.append(frame_referencia)
    if frame_imagen is not None:
        sets.append("frame_imagen = %s")
        params.append(psycopg2.Binary(frame_imagen))
        sets.append("frame_mime = %s")
        params.append(frame_mime)
    if zonas is not None:
        sets.append("zonas = %s::jsonb")
        params.append(json.dumps(zonas))
    if umbral_medio is not None:
        sets.append("umbral_medio = %s")
        params.append(umbral_medio)
    if umbral_alto is not None:
        sets.append("umbral_alto = %s")
        params.append(umbral_alto)
    if ventana_segundos is not None:
        sets.append("ventana_segundos = %s")
        params.append(ventana_segundos)
    if cooldown_segundos is not None:
        sets.append("cooldown_segundos = %s")
        params.append(cooldown_segundos)

    params.append(zona_id)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE configuraciones_zonas_exclusion
                SET {', '.join(sets)}
                WHERE id = %s
                RETURNING {_COLS}
                """,
                params,
            )
            return cur.fetchone()


def delete_zona(zona_id: int) -> tuple | None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE configuraciones_zonas_exclusion
                SET activa = FALSE, fecha_actualizacion = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING {_COLS}
                """,
                (zona_id,),
            )
            row = cur.fetchone()
            # El borrado es lógico (activa = FALSE), así que la FK ON DELETE
            # SET NULL de camaras_ip nunca se dispara: sin esto, las cámaras
            # seguían apuntando a una zona inactiva y no se podían monitorear.
            cur.execute(
                "UPDATE camaras_ip SET zona_exclusion_id = NULL WHERE zona_exclusion_id = %s",
                (zona_id,),
            )
            return row
