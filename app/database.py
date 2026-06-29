import logging
from contextlib import contextmanager

import psycopg2
from psycopg2 import pool

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Pool de conexiones: reutiliza conexiones en vez de abrir/cerrar una
# por cada request. ThreadedConnectionPool es thread-safe (FastAPI usa threads).
_pool: pool.ThreadedConnectionPool | None = None


def init_pool() -> None:
    """Inicializa el pool al arrancar la app (llamado desde main.py)."""
    global _pool
    _pool = pool.ThreadedConnectionPool(
        minconn=2,
        maxconn=10,
        dsn=settings.database_url,
    )
    logger.info("Pool de conexiones inicializado (min=2, max=10)")


def close_pool() -> None:
    """Cierra todas las conexiones al apagar la app."""
    if _pool:
        _pool.closeall()
        logger.info("Pool de conexiones cerrado")


@contextmanager
def get_db():
    """
    Context manager que obtiene una conexión del pool, hace commit
    automático al salir sin error, o rollback si ocurre una excepción.

    Uso:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(...)
    """
    if _pool is None:
        raise RuntimeError("El pool de BD no ha sido inicializado. Llama init_pool() primero.")

    conn = _pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)
