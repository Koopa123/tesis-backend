from app.database import get_db


def create_user(nombre: str, email: str, password_hash: str, rol: str = "vigilante") -> tuple:
    """Inserta un usuario y retorna (id, nombre, email, rol)."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO usuarios (nombre, email, password_hash, rol)
                VALUES (%s, %s, %s, %s)
                RETURNING id, nombre, email, rol
                """,
                (nombre, email, password_hash, rol),
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
