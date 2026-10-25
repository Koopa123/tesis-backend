from app.database import get_db

_COLS = (
    "id, sesion_id, usuario_id, zona_config_id, nivel, personas, "
    "atendida, fecha_alerta, fecha_atencion, camara_id, clip_evidencia"
)

# Con nombre de cámara (para listar/ver una alerta) — LEFT JOIN porque las
# alertas de sesión de navegador no tienen camara_id directo (viene de la
# sesión, no de la alerta), y las del edge sí lo traen.
_COLS_JOIN = (
    "a.id, a.sesion_id, a.usuario_id, a.zona_config_id, a.nivel, a.personas, "
    "a.atendida, a.fecha_alerta, a.fecha_atencion, a.camara_id, c.nombre, "
    "a.clip_evidencia, a.atendida_por, u.nombre"
)

_JOINS = (
    "LEFT JOIN camaras_ip c ON c.id = a.camara_id "
    "LEFT JOIN usuarios u ON u.id = a.atendida_por"
)


def crear_alerta(
    sesion_id: int | None,
    usuario_id: int | None,
    zona_config_id: int | None,
    nivel: str,
    personas: int,
    camara_id: int | None = None,
) -> tuple:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO alertas
                    (sesion_id, usuario_id, zona_config_id, nivel, personas, camara_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING {_COLS}
                """,
                (sesion_id, usuario_id, zona_config_id, nivel, personas, camara_id),
            )
            return cur.fetchone()


def get_alerta(alerta_id: int) -> tuple | None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {_COLS_JOIN} FROM alertas a
                {_JOINS}
                WHERE a.id = %s
                """,
                (alerta_id,),
            )
            return cur.fetchone()


def marcar_atendida(alerta_id: int, usuario_id: int) -> tuple | None:
    """Marca la alerta como atendida por usuario_id. Si ya estaba atendida,
    conserva quién y cuándo la atendió primero. Devuelve la fila con JOIN."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE alertas
                SET atendida = TRUE,
                    fecha_atencion = COALESCE(fecha_atencion, NOW()),
                    atendida_por = COALESCE(atendida_por, %s)
                WHERE id = %s
                """,
                (usuario_id, alerta_id),
            )
    return get_alerta(alerta_id)


def actualizar_clip(alerta_id: int, ruta: str) -> None:
    """Guarda la ruta del clip de video de evidencia una vez que el hilo en
    background terminó de escribirlo (ver yolo_detector.escribir_clip)."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE alertas SET clip_evidencia = %s WHERE id = %s",
                (ruta, alerta_id),
            )


def list_clips_vencidos(dias: int) -> list[tuple]:
    """(id, clip_evidencia) de alertas con clip más antiguo que `dias`."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, clip_evidencia FROM alertas
                WHERE clip_evidencia IS NOT NULL
                  AND fecha_alerta < NOW() - make_interval(days => %s)
                """,
                (dias,),
            )
            return cur.fetchall()


def quitar_clip(alerta_id: int) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE alertas SET clip_evidencia = NULL WHERE id = %s", (alerta_id,))


def list_alertas(
    usuario_id: int | None = None,
    atendida: bool | None = None,
    limit: int = 100,
) -> list[tuple]:
    """usuario_id=None devuelve las de todos (lo normal: las alertas son del equipo). Filtrables por estado atendida."""
    conditions: list[str] = []
    params: list = []

    if usuario_id is not None:
        conditions.append("a.usuario_id = %s")
        params.append(usuario_id)
    if atendida is not None:
        conditions.append("a.atendida = %s")
        params.append(atendida)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {_COLS_JOIN} FROM alertas a
                {_JOINS}
                {where}
                ORDER BY a.fecha_alerta DESC
                LIMIT %s
                """,
                params,
            )
            return cur.fetchall()
