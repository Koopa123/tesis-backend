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
        # Mantiene viva la conexión TCP y detecta conexiones muertas rápido
        # (el pooler de Supabase cierra conexiones inactivas silenciosamente).
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=5,
    )
    logger.info("Pool de conexiones inicializado (min=2, max=10)")


def _get_healthy_conn():
    """
    Obtiene una conexión del pool, descartando y reemplazando las que
    estén muertas (cerradas por el pooler o por un corte de red/DNS).
    """
    last_error: Exception | None = None
    for _ in range(3):
        conn = _pool.getconn()
        if conn.closed:
            _pool.putconn(conn, close=True)
            continue
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            return conn
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as exc:
            last_error = exc
            _pool.putconn(conn, close=True)
    raise RuntimeError("No se pudo obtener una conexión saludable del pool de BD") from last_error


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

    conn = _get_healthy_conn()
    conn_broken = False
    try:
        yield conn
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except (psycopg2.OperationalError, psycopg2.InterfaceError):
            # La conexión murió a mitad de la operación (corte de red/DNS, o
            # el pooler la cerró) — no hay nada que revertir. Se descarta del
            # pool y se deja propagar la excepción ORIGINAL, no esta: si no,
            # el fallo real (ej. el error de red) queda tapado por un
            # "connection already closed" que no dice qué pasó en realidad.
            conn_broken = True
        raise
    finally:
        _pool.putconn(conn, close=conn_broken)
