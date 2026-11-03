"""
Agente Edge — corre en la laptop del local (arquitectura edge/cloud).

Se conecta directo a las cámaras RTSP de la red interna y corre YOLO+BFS
localmente, reutilizando detector/yolo_detector.py (el mismo código que ya
funciona en local, con GPU). NO manda video a internet: solo reporta el
resultado calculado (personas, nivel, alerta) al backend en la nube, vía
POST /api/edge/deteccion autenticado con una clave de dispositivo
(X-Edge-Api-Key) — ver app/core/security.py::require_edge_key.

Uso:
    1. Copiar edge_config.example.json a edge_config.json y completarlo:
       - cloud_api_url: la URL de Railway (ej. https://tesis-backend-production-6ece.up.railway.app)
       - edge_api_key: el mismo valor que EDGE_API_KEY en las variables de Railway
       - camaras: una entrada por cámara, con el camara_id que YA tiene
         registrado en la tabla camaras_ip de la nube (créala antes desde el
         frontend, como cualquier cámara IP) y su rtsp_url.
    2. Ejecutar desde tesis-backend/, con el mismo venv que usa el backend
       (necesita torch/cv2/ultralytics ya instalados y probados en esta laptop):
           python edge_agent.py

Este script es un proceso aparte, sin FastAPI ni conexión a la base de
datos — pensado para quedar corriendo indefinidamente en la laptop.

Si el back-end local también está corriendo (Iniciar CrowdSense) y alguien
abre una cámara en Multi-cámara, el back-end ya la está analizando. Para no
analizarla dos veces (doble conexión RTSP, doble GPU y alertas repetidas), el
agente consulta cada 2 s GET /api/edge/local del back-end local
("local_api_url" en edge_config.json, por defecto http://127.0.0.1:8000): si
la cámara aparece ahí, cierra su propia conexión y solo reenvía a la nube ese
resultado; cuando la sesión local termina, vuelve a analizarla por su cuenta.
El back-end local necesita la misma EDGE_API_KEY en su .env.
"""

import base64
import json
import logging
import sys
import threading
import time
from pathlib import Path

import requests

from detector.yolo_detector import SesionAnalisisState, procesar_rtsp_mjpeg, warmup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger("edge_agent")

CONFIG_PATH = Path(__file__).parent / "edge_config.json"

# Intervalo mínimo entre reportes "normales" (sin alerta) a la nube, para no
# saturar la API con un POST por cada frame (~25/seg). Las alertas se
# reportan de inmediato, sin esperar este intervalo.
REPORTE_INTERVALO_SEG = 5.0

# Cada cuánto se pregunta al back-end local qué cámaras ya está analizando.
VIGIA_INTERVALO_SEG = 2.0
# Un resultado local más viejo que esto (cámara caída) no se reenvía.
RESULTADO_MAX_EDAD_SEG = 10.0


class VigiaLocal:
    """Sabe qué cámaras está analizando el back-end de esta misma laptop."""

    def __init__(self, url: str, api_key: str):
        self.url = url.rstrip("/")
        self.headers = {"X-Edge-Api-Key": api_key}
        self._camaras: dict[int, dict] = {}
        self._lock = threading.Lock()
        self._http = requests.Session()

    def ciclo(self) -> None:
        avisado = False
        while True:
            try:
                resp = self._http.get(f"{self.url}/api/edge/local", headers=self.headers, timeout=3)
                resp.raise_for_status()
                consultado = time.time()
                camaras = {c["camara_id"]: {**c, "consultado": consultado} for c in resp.json()["camaras"]}
                avisado = False
            except (requests.RequestException, ValueError, KeyError) as exc:
                # Back-end local apagado o sin la clave: el agente analiza todo.
                if not avisado:
                    logger.info("Back-end local no disponible (%s); el agente analiza todas las cámaras.", exc)
                    avisado = True
                camaras = {}
            with self._lock:
                self._camaras = camaras
            time.sleep(VIGIA_INTERVALO_SEG)

    def sesion(self, camara_id: int) -> dict | None:
        with self._lock:
            return self._camaras.get(camara_id)

    def foto_alerta(self, camara_id: int) -> bytes | None:
        try:
            resp = self._http.get(f"{self.url}/api/edge/local/{camara_id}/foto-alerta",
                                  headers=self.headers, timeout=3)
            return resp.content if resp.status_code == 200 else None
        except requests.RequestException:
            return None


def cargar_config() -> dict:
    if not CONFIG_PATH.exists():
        logger.error(
            "No existe %s. Copia edge_config.example.json y complétalo.", CONFIG_PATH
        )
        sys.exit(1)
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def reportar(session: requests.Session, api_url: str, api_key: str, payload: dict) -> None:
    try:
        resp = session.post(
            f"{api_url}/api/edge/deteccion",
            json=payload,
            headers={"X-Edge-Api-Key": api_key},
            timeout=10,
        )
        if resp.status_code >= 400:
            logger.warning(
                "La nube rechazó el reporte (camara_id=%s): %s %s",
                payload["camara_id"], resp.status_code, resp.text[:200],
            )
    except requests.RequestException as exc:
        # No hay internet en este momento, o el backend en la nube está caído.
        # No es fatal: la detección local sigue funcionando, solo se pierde
        # este reporte puntual — el siguiente reporte periódico refleja el
        # estado actual de todas formas.
        logger.warning("No se pudo reportar a la nube (camara_id=%s): %s", payload["camara_id"], exc)


def _reenviar_sesion_local(cam: dict, vigia: VigiaLocal, api_url: str, api_key: str,
                           session: requests.Session) -> None:
    """Mientras el back-end local analiza la cámara, solo reenvía su resultado a la nube."""
    camara_id = cam["camara_id"]
    ultimo_reporte = 0.0
    ultima_alerta = None
    primera = True
    while True:
        info = vigia.sesion(camara_id)
        if info is None:
            return
        if primera:
            # La alerta que ya tenía la sesión al empezar a reenviar no es nueva.
            ultima_alerta, primera = info["ultima_alerta_id"], False
        ahora = time.time()
        nueva_alerta = info["ultima_alerta_id"] is not None and info["ultima_alerta_id"] != ultima_alerta
        edad = info["edad_seg"] + (ahora - info["consultado"])
        if edad <= RESULTADO_MAX_EDAD_SEG and (nueva_alerta or ahora - ultimo_reporte >= REPORTE_INTERVALO_SEG):
            payload = {
                "camara_id": camara_id,
                "zona_config_id": info["zona_config_id"] if info["zona_config_id"] is not None else cam.get("zona_config_id"),
                "personas": info["personas"],
                "nivel": info["nivel"],
                "alerta": nueva_alerta,
            }
            if nueva_alerta:
                foto = vigia.foto_alerta(camara_id)
                if foto:
                    payload["frame_evidencia_b64"] = base64.b64encode(foto).decode("ascii")
            ultima_alerta = info["ultima_alerta_id"]
            ultimo_reporte = ahora
            reportar(session, api_url, api_key, payload)
        time.sleep(1)


def _monitorear_camara(cam: dict, api_url: str, api_key: str, session: requests.Session,
                       vigia: VigiaLocal) -> None:
    camara_id = cam["camara_id"]
    rtsp_url = cam["rtsp_url"]
    zona_config = cam.get("zona_config")  # None => usa umbrales por defecto (4/6)
    zona_config_id = cam.get("zona_config_id")

    estado = SesionAnalisisState(zona_config=zona_config)
    ultimo_reporte = 0.0

    def on_frame(jpeg_bytes, resultado, alerta):
        nonlocal ultimo_reporte

        if resultado.get("tipo") == "error":
            logger.error("Cámara %s: %s", camara_id, resultado.get("mensaje"))
            return

        ahora = time.time()
        es_periodico = ahora - ultimo_reporte >= REPORTE_INTERVALO_SEG
        if not (alerta or es_periodico):
            return

        payload = {
            "camara_id": camara_id,
            "zona_config_id": zona_config_id,
            "personas": resultado["personas"],
            "nivel": resultado["nivel"],
            "alerta": bool(alerta),
        }
        if alerta and jpeg_bytes:
            payload["frame_evidencia_b64"] = base64.b64encode(jpeg_bytes).decode("ascii")

        ultimo_reporte = ahora
        reportar(session, api_url, api_key, payload)

    def local_activa() -> bool:
        return vigia.sesion(camara_id) is not None

    # Reintenta indefinidamente si la cámara/RTSP se cae — procesar_rtsp_mjpeg
    # termina tras 3 fallos de lectura seguidos, así que este bucle exterior
    # es lo que sostiene el monitoreo "24/7" ante cortes de red/cámara.
    while True:
        if local_activa():
            logger.info("Cámara %s: la analiza el back-end local; el agente solo reenvía su resultado.", camara_id)
            _reenviar_sesion_local(cam, vigia, api_url, api_key, session)
            logger.info("Cámara %s: terminó la sesión local; el agente vuelve a analizarla.", camara_id)
            continue
        logger.info("Cámara %s: conectando...", camara_id)
        try:
            procesar_rtsp_mjpeg(
                rtsp_url=rtsp_url,
                zona_config=zona_config,
                estado=estado,
                cancelado_fn=local_activa,
                on_frame=on_frame,
            )
        except Exception:
            logger.exception("Cámara %s: error inesperado en el hilo de análisis", camara_id)
        if local_activa():
            continue
        logger.warning("Cámara %s: stream cortado, reintentando en 5s...", camara_id)
        time.sleep(5)


def main() -> None:
    config = cargar_config()
    api_url = config["cloud_api_url"].rstrip("/")
    api_key = config["edge_api_key"]
    camaras = config.get("camaras", [])

    if not camaras:
        logger.error("edge_config.json no tiene cámaras configuradas.")
        sys.exit(1)

    logger.info("Precargando modelo YOLO...")
    warmup()

    session = requests.Session()
    vigia = VigiaLocal(config.get("local_api_url", "http://127.0.0.1:8000"), api_key)
    threading.Thread(target=vigia.ciclo, daemon=True, name="vigia-local").start()
    hilos = []
    for cam in camaras:
        t = threading.Thread(
            target=_monitorear_camara,
            args=(cam, api_url, api_key, session, vigia),
            daemon=True,
            name=f"camara-{cam['camara_id']}",
        )
        t.start()
        hilos.append(t)

    logger.info("Agente edge corriendo (%d cámara(s)). Ctrl+C para detener.", len(hilos))
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Deteniendo agente edge...")


if __name__ == "__main__":
    main()
