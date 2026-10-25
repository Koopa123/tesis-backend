"""
Borrado automático de evidencias vencidas (fotos de sesión y clips de alerta).

El D.S. 007-2020-IN obliga a un establecimiento comercial a conservar lo grabado
al menos 45 días, y la Directiva 01-2020-JUS/DGTAIPD fija el máximo en 60. Pasado
`retencion_dias` (60 por defecto), el sistema borra el archivo y quita la
referencia en la BD.

Las grabaciones que sube el usuario NO se borran aquí: son material que alguien
cargó a propósito para analizarlo y las elimina su dueño o un administrador.

Corre en la laptop y en Railway, porque las dos usan la misma BD:
- donde está el archivo, se borra por la referencia de la BD;
- si la otra instancia ya quitó la referencia, el archivo queda huérfano y se
  borra por su fecha de modificación al recorrer uploads/evidencias.
"""
import logging
import os
import threading
import time

from app.config import get_settings
from app.core.auditoria import auditar
from app.repositories import alerta_repo, analisis_repo

logger = logging.getLogger(__name__)

CARPETA = "uploads/evidencias"
INTERVALO_SEGUNDOS = 24 * 3600
_detener = threading.Event()


def _borrar(ruta: str | None) -> bool:
    if not ruta:
        return False
    try:
        if os.path.exists(ruta):
            os.remove(ruta)
            return True
    except OSError:
        logger.exception("No se pudo borrar la evidencia %s", ruta)
    return False


def borrar_vencidas(dias: int) -> dict:
    """Borra las evidencias con más de `dias` días. Devuelve cuántas se tocaron."""
    fotos = clips = huerfanos = 0
    for resultado_id, ruta in analisis_repo.list_evidencias_vencidas(dias):
        _borrar(ruta)
        analisis_repo.quitar_evidencia(resultado_id)
        fotos += 1
    for alerta_id, ruta in alerta_repo.list_clips_vencidos(dias):
        _borrar(ruta)
        alerta_repo.quitar_clip(alerta_id)
        clips += 1
    if os.path.isdir(CARPETA):
        limite = time.time() - dias * 86400
        for nombre in os.listdir(CARPETA):
            ruta = os.path.join(CARPETA, nombre)
            if os.path.isfile(ruta) and os.path.getmtime(ruta) < limite and _borrar(ruta):
                huerfanos += 1
    return {"fotos": fotos, "clips": clips, "huerfanos": huerfanos}


def _ciclo() -> None:
    dias = get_settings().retencion_dias
    # Esperar un poco tras el arranque para no competir con el warmup de YOLO.
    if _detener.wait(60):
        return
    while not _detener.is_set():
        try:
            n = borrar_vencidas(dias)
            if any(n.values()):
                logger.info("Retención de %d días: %s", dias, n)
                auditar(None, None, "borrado_automatico", "evidencias", None,
                        f"{n['fotos']} fotos, {n['clips']} clips y {n['huerfanos']} archivos huérfanos con más de {dias} días")
        except Exception:
            logger.exception("Error en el borrado automático de evidencias")
        if _detener.wait(INTERVALO_SEGUNDOS):
            return


def iniciar() -> None:
    if get_settings().retencion_dias <= 0:
        logger.info("Borrado automático de evidencias desactivado (RETENCION_DIAS=0)")
        return
    _detener.clear()
    threading.Thread(target=_ciclo, name="retencion-evidencias", daemon=True).start()


def detener() -> None:
    _detener.set()
