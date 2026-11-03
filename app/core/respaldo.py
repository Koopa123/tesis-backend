"""
Respaldo diario de la base de datos en el disco de la laptop del local.

Supabase en plan gratuito no guarda copias de seguridad, así que una tabla
borrada por error o una pérdida del proyecto no tendría vuelta atrás. Una vez
al día, si la máquina tiene `pg_dump`, se guarda `respaldos_bd/crowdsense_
AAAA-MM-DD.dump` (formato custom, se restaura con `pg_restore`) y se borran
los que pasan de `respaldo_dias`.

Solo corre donde hay `pg_dump`: en la laptop sí (viene con PostgreSQL); en
Railway no está instalado y el respaldo se omite sin error. Como la laptop
solo se enciende en horario de atención, el respaldo del día se toma al
arrancar el backend y, si ya existe el de hoy, no se repite.
"""
import glob
import logging
import os
import shutil
import subprocess
import threading
from datetime import date
from urllib.parse import unquote, urlparse

from app.config import get_settings
from app.core.auditoria import auditar

logger = logging.getLogger(__name__)

INTERVALO_SEGUNDOS = 24 * 3600
PREFIJO = "crowdsense_"
_detener = threading.Event()


def _buscar_pg_dump() -> str | None:
    configurado = get_settings().pg_dump_path
    if configurado:
        return configurado if os.path.isfile(configurado) else None
    encontrado = shutil.which("pg_dump")
    if encontrado:
        return encontrado
    # En Windows el instalador de PostgreSQL no agrega bin/ al PATH.
    candidatos = sorted(glob.glob(r"C:\Program Files\PostgreSQL\*\bin\pg_dump.exe"), reverse=True)
    return candidatos[0] if candidatos else None


def _entorno_conexion(database_url: str) -> dict:
    """Pasa la conexión por variables PG* para que la contraseña no quede en la línea de comandos."""
    u = urlparse(database_url)
    env = dict(os.environ)
    env.update({
        "PGHOST": u.hostname or "",
        "PGPORT": str(u.port or 5432),
        "PGUSER": unquote(u.username or ""),
        "PGPASSWORD": unquote(u.password or ""),
        "PGDATABASE": u.path.lstrip("/") or "postgres",
    })
    return env


def _podar(carpeta: str, dias: int) -> int:
    archivos = sorted(glob.glob(os.path.join(carpeta, f"{PREFIJO}*.dump")))
    sobrantes = archivos[:-dias] if dias > 0 else []
    for ruta in sobrantes:
        try:
            os.remove(ruta)
        except OSError:
            logger.exception("No se pudo borrar el respaldo viejo %s", ruta)
    return len(sobrantes)


def respaldar_hoy() -> str | None:
    """Guarda el respaldo de hoy si todavía no existe. Devuelve la ruta, o None si no hizo nada."""
    s = get_settings()
    pg_dump = _buscar_pg_dump()
    if not pg_dump:
        return None
    os.makedirs(s.respaldo_folder, exist_ok=True)
    destino = os.path.join(s.respaldo_folder, f"{PREFIJO}{date.today().isoformat()}.dump")
    if os.path.exists(destino):
        return None

    temporal = destino + ".parcial"
    resultado = subprocess.run(
        [pg_dump, "--schema=public", "--format=custom", "--no-owner", "--no-privileges", "-f", temporal],
        env=_entorno_conexion(s.database_url),
        capture_output=True, text=True, timeout=600,
    )
    if resultado.returncode != 0:
        if os.path.exists(temporal):
            os.remove(temporal)
        raise RuntimeError(f"pg_dump terminó con código {resultado.returncode}: {resultado.stderr.strip()[:300]}")
    # Recién al terminar bien toma su nombre final: un corte de luz a medias
    # deja un .parcial, nunca un respaldo roto con apariencia de bueno.
    os.replace(temporal, destino)
    podados = _podar(s.respaldo_folder, s.respaldo_dias)
    kb = os.path.getsize(destino) // 1024
    logger.info("Respaldo de la BD guardado en %s (%d KB, %d viejos borrados)", destino, kb, podados)
    auditar(None, None, "respaldo_bd", "base_de_datos", None, f"{os.path.basename(destino)} ({kb} KB)")
    return destino


def _ciclo() -> None:
    # Esperar un poco tras el arranque para no competir con el warmup de YOLO.
    if _detener.wait(90):
        return
    while not _detener.is_set():
        try:
            respaldar_hoy()
        except Exception:
            logger.exception("Error en el respaldo diario de la BD")
        if _detener.wait(INTERVALO_SEGUNDOS):
            return


def iniciar() -> None:
    if get_settings().respaldo_dias <= 0:
        logger.info("Respaldo diario de la BD desactivado (RESPALDO_DIAS=0)")
        return
    if not _buscar_pg_dump():
        logger.info("Respaldo diario de la BD omitido: pg_dump no está instalado en esta máquina")
        return
    _detener.clear()
    threading.Thread(target=_ciclo, name="respaldo-bd", daemon=True).start()


def detener() -> None:
    _detener.set()
