from app.database import get_db


def registrar(
    usuario_id: int | None,
    accion: str,
    recurso: str | None = None,
    recurso_id: int | None = None,
    detalle: str | None = None,
    ip: str | None = None,
) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO auditoria (usuario_id, accion, recurso, recurso_id, detalle, ip)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (usuario_id, accion, recurso, recurso_id, detalle, ip),
            )


def listar(accion: str | None = None, usuario_id: int | None = None, limit: int = 200) -> list[tuple]:
    """(id, fecha, usuario_id, usuario_nombre, accion, recurso, recurso_id, detalle, ip), más reciente primero."""
    condiciones, params = [], []
    if accion:
        condiciones.append("a.accion = %s")
        params.append(accion)
    if usuario_id is not None:
        condiciones.append("a.usuario_id = %s")
        params.append(usuario_id)
    where = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""
    params.append(limit)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT a.id, a.fecha, a.usuario_id, u.nombre, a.accion, a.recurso,
                       a.recurso_id, a.detalle, a.ip
                FROM auditoria a
                LEFT JOIN usuarios u ON u.id = a.usuario_id
                {where}
                ORDER BY a.fecha DESC
                LIMIT %s
                """,
                params,
            )
            return cur.fetchall()
