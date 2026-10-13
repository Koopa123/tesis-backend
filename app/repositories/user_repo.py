from app.database import get_db


def create_user(nombre: str, email: str, password_hash: str, rol: str = "vigilante", activo: bool = True) -> tuple:
    """Inserta un usuario y retorna (id, nombre, email, rol)."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO usuarios (nombre, email, password_hash, rol, activo)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, nombre, email, rol
                """,
                (nombre, email, password_hash, rol, activo),
            )
            return cur.fetchone()


def get_user_by_email(email: str) -> tuple | None:
    """Devuelve (id, nombre, email, password_hash, rol) o None si no existe."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, nombre, email, password_hash, rol
                FROM usuarios
                WHERE email = %s AND activo = TRUE
                """,
                (email,),
            )
            return cur.fetchone()


def get_user_by_id(user_id: int) -> tuple | None:
    """Devuelve (id, nombre, email, rol) o None."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, nombre, email, rol
                FROM usuarios
                WHERE id = %s AND activo = TRUE
                """,
                (user_id,),
            )
            return cur.fetchone()


def list_users() -> list[tuple]:
    """Todas las cuentas: (id, nombre, email, rol, activo, fecha_creacion).
    Primero las desactivadas (pendientes de activación), luego las más recientes."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, nombre, email, rol, activo, fecha_creacion
                FROM usuarios
                ORDER BY activo ASC, fecha_creacion DESC
                """
            )
            return cur.fetchall()


def get_user_any(user_id: int) -> tuple | None:
    """Como get_user_by_id pero sin filtrar por activo: (id, nombre, email, rol, activo, fecha_creacion)."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, nombre, email, rol, activo, fecha_creacion FROM usuarios WHERE id = %s",
                (user_id,),
            )
            return cur.fetchone()


def count_active_admins() -> int:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM usuarios WHERE rol = 'administrador' AND activo = TRUE")
            return cur.fetchone()[0]


def set_active(user_id: int, activo: bool) -> tuple | None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE usuarios SET activo = %s WHERE id = %s
                RETURNING id, nombre, email, rol, activo, fecha_creacion
                """,
                (activo, user_id),
            )
            return cur.fetchone()


def has_records(user_id: int) -> bool:
    """True si la cuenta tiene sesiones, grabaciones, alertas o zonas a su nombre.
    Las llaves foráneas son ON DELETE SET NULL: borrarla dejaría esos registros sin dueño."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT EXISTS (SELECT 1 FROM sesiones_monitoreo WHERE usuario_id = %(id)s)
                    OR EXISTS (SELECT 1 FROM grabaciones WHERE usuario_id = %(id)s)
                    OR EXISTS (SELECT 1 FROM alertas WHERE usuario_id = %(id)s)
                    OR EXISTS (SELECT 1 FROM configuraciones_zonas_exclusion WHERE creado_por = %(id)s)
                """,
                {"id": user_id},
            )
            return cur.fetchone()[0]


def delete_user(user_id: int) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM usuarios WHERE id = %s", (user_id,))
