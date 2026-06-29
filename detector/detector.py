import logging
import math
import os

import cv2
from ultralytics import YOLO

logger = logging.getLogger(__name__)

# ── Configuración ─────────────────────────────────────────────────────────────

CONFIANZA_MINIMA = 0.50
DISTANCIA_AGRUPACION_FALLBACK = 100
FACTOR_DISTANCIA_AGRUPACION = 1.5
UMBRAL_MEDIO = 4   # Grupo de 2-4 personas → MEDIO
UMBRAL_ALTO = 6    # Grupo de 6+ personas  → ALTO

# ── Modelo ────────────────────────────────────────────────────────────────────

def _cargar_modelo() -> YOLO:
    logger.info("Cargando modelo YOLOv8...")
    return YOLO("yolov8s.pt")


modelo = _cargar_modelo()


# ── Detección ─────────────────────────────────────────────────────────────────

def _en_zona_ignorada(x1: int, y1: int, x2: int, y2: int, zonas: list) -> bool:
    cx = (x1 + x2) // 2
    cy = (y1 + y2) // 2
    return any(zx1 <= cx <= zx2 and zy1 <= cy <= zy2 for zx1, zy1, zx2, zy2 in zonas)


def detectar_personas(frame, zonas: list) -> list[dict]:
    resultados = modelo(frame, verbose=False)
    personas = []

    for resultado in resultados:
        for caja in resultado.boxes:
            if int(caja.cls[0]) != 0:              # solo clase "person"
                continue
            confianza = float(caja.conf[0])
            if confianza < CONFIANZA_MINIMA:
                continue

            x1, y1, x2, y2 = map(int, caja.xyxy[0])
            if _en_zona_ignorada(x1, y1, x2, y2, zonas):
                continue

            personas.append({
                "bbox": (x1, y1, x2, y2),
                "centro": ((x1 + x2) // 2, (y1 + y2) // 2),
                "confianza": confianza,
                "ancho": x2 - x1,
            })

    return personas


# ── Agrupación ────────────────────────────────────────────────────────────────

def _distancia(p1: tuple, p2: tuple) -> float:
    return math.hypot(p2[0] - p1[0], p2[1] - p1[1])


def distancia_adaptativa(personas: list[dict]) -> float:
    """
    Umbral de agrupación basado en el ancho promedio de las bounding boxes.
    Se auto-ajusta al zoom del video: más zoom → cajas más grandes → umbral mayor.
    """
    anchos = [p["ancho"] for p in personas if p["ancho"] > 0]
    if len(anchos) < 2:
        return DISTANCIA_AGRUPACION_FALLBACK
    return (sum(anchos) / len(anchos)) * FACTOR_DISTANCIA_AGRUPACION


def agrupar_personas(personas: list[dict], umbral: float) -> list[list[int]]:
    """BFS para agrupar personas cuyo centro está a menos de `umbral` píxeles."""
    grupos: list[list[int]] = []
    visitados: set[int] = set()

    for i in range(len(personas)):
        if i in visitados:
            continue
        cola = [i]
        visitados.add(i)
        grupo: list[int] = []

        while cola:
            idx = cola.pop(0)
            grupo.append(idx)
            for j in range(len(personas)):
                if j not in visitados and _distancia(personas[idx]["centro"], personas[j]["centro"]) <= umbral:
                    visitados.add(j)
                    cola.append(j)

        grupos.append(grupo)

    return grupos


def grupo_mas_grande(grupos: list[list[int]]) -> int:
    return max((len(g) for g in grupos), default=0)


# ── Clasificación ─────────────────────────────────────────────────────────────

def clasificar(n: int) -> tuple[str, tuple[int, int, int]]:
    if n < UMBRAL_MEDIO:
        return "BAJO",  (0, 255, 0)
    if n < UMBRAL_ALTO:
        return "MEDIO", (0, 255, 255)
    return "ALTO", (0, 0, 255)


# ── Dibujo ────────────────────────────────────────────────────────────────────

def _dibujar(frame, personas, grupos, umbral, nivel, color, preset_nombre):
    for p in personas:
        x1, y1, x2, y2 = p["bbox"]
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.circle(frame, p["centro"], 4, (255, 0, 0), -1)
        cv2.putText(frame, f"{p['confianza']:.2f}", (x1, y1 - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

    for grupo in grupos:
        if len(grupo) <= 1:
            continue
        puntos = [personas[i]["centro"] for i in grupo]
        for i in range(len(puntos)):
            for j in range(i + 1, len(puntos)):
                if _distancia(puntos[i], puntos[j]) <= umbral:
                    cv2.line(frame, puntos[i], puntos[j], (255, 255, 0), 1)

    if preset_nombre:
        cv2.putText(frame, f"Preset: {preset_nombre}", (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 2)

    cv2.putText(frame, f"Personas: {len(personas)}", (10, 55),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    cv2.putText(frame, f"Grupo mayor: {grupo_mas_grande(grupos)}", (10, 85),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
    cv2.putText(frame, f"Nivel: {nivel}", (10, 115),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

    if nivel == "ALTO":
        cv2.putText(frame, "⚠ AGLOMERACION DETECTADA", (10, 150),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)


def _dibujar_zonas(frame, zonas: list):
    for zx1, zy1, zx2, zy2 in zonas:
        cv2.rectangle(frame, (zx1, zy1), (zx2, zy2), (80, 80, 80), 1)


# ── Stream principal ──────────────────────────────────────────────────────────

def generar_stream_video(
    ruta_entrada: str,
    nombre_video: str = "video",
    zonas: list | None = None,
    preset_id: int | None = None,
    preset_nombre: str | None = None,
):
    """
    Generador que emite frames MJPEG con detecciones superpuestas.
    Al terminar, guarda el resultado en BD y borra el video del disco.
    """
    # Importación diferida para evitar ciclo (detector → db → detector)
    from app.repositories.analisis_repo import save_analisis

    zonas = zonas or []
    cap = cv2.VideoCapture(ruta_entrada)
    if not cap.isOpened():
        raise RuntimeError(f"No se pudo abrir el video: {ruta_entrada}")

    max_personas = 0
    max_grupo = 0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            personas = detectar_personas(frame, zonas)
            umbral = distancia_adaptativa(personas)
            grupos = agrupar_personas(personas, umbral)
            n_grupo = grupo_mas_grande(grupos)
            nivel, color = clasificar(n_grupo)

            max_personas = max(max_personas, len(personas))
            max_grupo = max(max_grupo, n_grupo)

            _dibujar(frame, personas, grupos, umbral, nivel, color, preset_nombre)
            _dibujar_zonas(frame, zonas)

            ok, buffer = cv2.imencode(".jpg", frame)
            if not ok:
                continue

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + buffer.tobytes()
                + b"\r\n"
            )

    finally:
        cap.release()

        try:
            if os.path.exists(ruta_entrada):
                os.remove(ruta_entrada)
        except OSError as e:
            logger.warning("No se pudo borrar %s: %s", ruta_entrada, e)

        nivel_final, _ = clasificar(max_grupo)
        try:
            save_analisis(nombre_video, max_personas, max_grupo, nivel_final, preset_id)
        except Exception as e:
            logger.error("No se pudo guardar el análisis en BD: %s", e)
