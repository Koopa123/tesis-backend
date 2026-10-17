"""
Cierre de una sesión de cámara IP: guarda su resultado en el historial y la
marca como detenida.

Lo llama el hilo RTSP cuando termina, sea porque nadie la mira durante el
período de gracia, porque se abrió una sesión nueva para la misma cámara o
porque alguien la detuvo por la API. Es idempotente: eliminar_estado() saca
el estado una sola vez, así que el resultado nunca se guarda dos veces.
"""

import datetime
import logging
import os

from app.repositories import analisis_repo, monitoreo_repo
from detector.yolo_detector import eliminar_estado

logger = logging.getLogger(__name__)


def finalizar_sesion_camara(sesion_id: int, zona_id: int | None) -> tuple | None:
    estado = eliminar_estado(sesion_id)
    if estado and estado.frames_procesados > 0:
        # RF-5.2: persistir el fotograma con mayor concentración si existe
        evidencia_path = None
        if estado.frame_evidencia_bytes:
            try:
                os.makedirs("uploads/evidencias", exist_ok=True)
                evidencia_path = f"uploads/evidencias/sesion_{sesion_id}.jpg"
                with open(evidencia_path, "wb") as f:
                    f.write(estado.frame_evidencia_bytes)
            except Exception:
                logger.exception("Error al guardar frame de evidencia (sesion_id=%s)", sesion_id)
                evidencia_path = None

        analisis_repo.save_resultado(
            sesion_id=sesion_id,
            zona_config_id=zona_id,
            personas_maximas=estado.personas_maximas,
            nivel_maximo=estado.nivel_maximo,
            tiempo_primera_media_seg=estado.tiempo_primera_media,
            alerta_activada=estado.alerta_activada,
            frames_procesados=estado.frames_procesados,
            inicio_analisis=datetime.datetime.fromtimestamp(estado.inicio).isoformat(),
            fin_analisis=datetime.datetime.now().isoformat(),
            frame_evidencia=evidencia_path,
        )

    sesion = monitoreo_repo.get_sesion(sesion_id)
    if sesion is not None and sesion[6] == "activo":   # sesion[6] = estado
        sesion = monitoreo_repo.detener_sesion(sesion_id)
    return sesion
