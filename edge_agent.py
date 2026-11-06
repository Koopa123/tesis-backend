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
Cuando el agente analiza por su cuenta y detecta una alerta, la registra en el
back-end local (suena en la laptop) y le adjunta el clip de 8 s, igual que
haría una sesión de Multi-cámara.
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

from app.core.senal import SeguimientoSenal
from detector.yolo_detector import SesionAnalisisState, escribir_clip, procesar_rtsp_mjpeg, warmup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger("edge_agent")

CONFIG_PATH = Path(__file__).parent / "edge_config.json"
# La misma carpeta que usa el back-end local: los clips del agente se sirven igual.
EVIDENCIAS = Path(__file__).parent / "uploads" / "evidencias"

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

    def registrar_alerta(self, datos: dict) -> dict | None:
        """Registra la alerta en el back-end local (suena en la laptop). None si no responde."""
        try:
            resp = self._http.post(f"{self.url}/api/edge/local/alerta", json=datos,
                                   headers=self.headers, timeout=5)
            return resp.json() if resp.status_code == 200 else None
        except (requests.RequestException, ValueError):
            return None

    def adjuntar_clip(self, alerta_id: int, archivo: str) -> bool:
        try:
            resp = self._http.put(f"{self.url}/api/edge/local/alerta/{alerta_id}/clip",
                                  json={"archivo": archivo}, headers=self.headers, timeout=5)
            return resp.status_code == 204
        except requests.RequestException:
            return False

    def registrar_evento(self, camara_id: int, evento: str, detalle: str | None) -> None:
        """Corte o reconexión de una cámara, para la auditoría del back-end local."""
        try:
            self._http.post(f"{self.url}/api/edge/local/evento",
                            json={"camara_id": camara_id, "evento": evento, "detalle": detalle},
                            headers=self.headers, timeout=5)
        except requests.RequestException:
            logger.warning("Cámara %s: no se pudo registrar el evento %s", camara_id, evento)

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


def _alerta_propia(payload: dict, clip: list | None, vigia: VigiaLocal,
                   api_url: str, api_key: str, session: requests.Session) -> None:
    """
    Alerta que detectó el propio agente (nadie tenía la cámara abierta).
    1) Se registra en el back-end local, para que suene en la laptop.
    2) Se reporta a la nube, que reutiliza esa misma alerta y avisa a los
       usuarios remotos (crear_alerta_sin_duplicar).
    3) Se graba el clip con los últimos 8 s que ya estaban en memoria y se
       adjunta a la alerta. Es lo único lento, por eso va al final.
    Si el back-end local no responde, la alerta llega igual por la nube, sin clip.
    """
    camara_id = payload["camara_id"]
    local = vigia.registrar_alerta({k: payload[k] for k in ("camara_id", "zona_config_id", "personas", "nivel")})
    reportar(session, api_url, api_key, payload)
    if local is None:
        logger.warning("Cámara %s: el back-end local no respondió; la alerta queda sin clip.", camara_id)
        return
    if local.get("tiene_clip") or not clip:
        return
    try:
        EVIDENCIAS.mkdir(parents=True, exist_ok=True)
        ruta = escribir_clip(clip, str(EVIDENCIAS / f"alerta_{local['id']}.mp4"))
    except Exception:
        logger.exception("Cámara %s: no se pudo grabar el clip de la alerta %s", camara_id, local["id"])
        return
    if ruta and vigia.adjuntar_clip(local["id"], Path(ruta).name):
        logger.info("Cámara %s: clip de la alerta %s guardado.", camara_id, local["id"])
    else:
        logger.warning("Cámara %s: no se pudo adjuntar el clip de la alerta %s.", camara_id, local["id"])


def _monitorear_camara(cam: dict, api_url: str, api_key: str, session: requests.Session,
                       vigia: VigiaLocal) -> None:
    camara_id = cam["camara_id"]
    rtsp_url = cam["rtsp_url"]
    zona_config = cam.get("zona_config")  # None => usa umbrales por defecto (4/6)
    zona_config_id = cam.get("zona_config_id")

    estado = SesionAnalisisState(zona_config=zona_config)
    ultimo_reporte = 0.0
    # Cortes y reconexiones mientras el agente analiza la cámara por su cuenta.
    senal = SeguimientoSenal(lambda evento, detalle: vigia.registrar_evento(camara_id, evento, detalle))

    def on_frame(jpeg_bytes, resultado, alerta):
        nonlocal ultimo_reporte

        if resultado.get("tipo") == "error":
            logger.error("Cámara %s: %s", camara_id, resultado.get("mensaje"))
            return
        senal.cuadro_recibido()

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
        if alerta:
            # El búfer de 8 s se copió al confirmarse la alerta (estado.actualizar).
            clip, estado.clip_pendiente = estado.clip_pendiente, None
            threading.Thread(target=_alerta_propia, daemon=True,
                             args=(payload, clip, vigia, api_url, api_key, session)).start()
        else:
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
        senal.conexion_perdida()
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
