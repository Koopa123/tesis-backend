"""
Edge (laptop en el local) — arquitectura edge/cloud.

La laptop del local corre YOLO/OpenCV directo contra las cámaras RTSP de la
red interna y NO manda video a la nube: solo reporta el resultado ya
calculado (personas, nivel, alerta). Esta laptop no tiene un usuario
logueado en un navegador, así que no usa JWT — usa una clave de dispositivo
fija (X-Edge-Api-Key, ver app/core/security.py::require_edge_key).

POST /api/edge/deteccion              → reporta el estado de una cámara (auth: API key)
GET  /api/edge/estado                 → estado en vivo de todas las cámaras (auth: usuario)
GET  /api/edge/estado/{id}/evidencia  → última foto de evidencia en base64 (auth: usuario)
GET  /api/edge/local                  → cámaras que este back-end ya analiza (auth: API key)
GET  /api/edge/local/{id}/foto-alerta → foto de la última alerta de esa sesión (auth: API key)
POST /api/edge/local/alerta           → el agente registra su alerta y avisa en la laptop (auth: API key)
PUT  /api/edge/local/alerta/{id}/clip → el agente adjunta el clip de 8 s que grabó (auth: API key)

Las dos rutas /local las consulta el agente en la misma laptop: si el back-end
local ya tiene una sesión viva de una cámara (alguien abrió Multi-cámara), el
agente cierra su propia conexión RTSP y solo reenvía a la nube ese resultado.
Así cada cámara se analiza una sola vez. En Railway esas listas salen vacías.
"""

import logging
import os
import re
import time

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from app.core.rtsp_manager import sesiones_de_camara
from app.core.security import require_auth, require_edge_key
from app.core.sse_manager import alerta_manager
from app.models.schemas import EdgeDeteccionIn, EstadoCamarasOut
from app.repositories import alerta_repo, camara_repo, edge_repo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/edge", tags=["Edge (laptop local)"])


def _row_estado(r: tuple) -> dict:
    # 0=camara_id, 1=zona_config_id, 2=personas, 3=nivel, 4=alerta_activa,
    # 5=frame_evidencia_b64, 6=fecha_actualizacion, 7=nombre, 8=ubicacion
    return {
        "camara_id": r[0],
        "camara_nombre": r[7],
        "ubicacion": r[8],
        "zona_config_id": r[1],
        "personas": r[2],
        "nivel": r[3],
        "alerta_activa": r[4],
        "tiene_evidencia": r[5] is not None,
        "fecha_actualizacion": r[6].isoformat() if r[6] else None,
    }


# ── POST /deteccion — reporte de la laptop ───────────────────────────────────

@router.post("/deteccion", status_code=204)
async def reportar_deteccion(
    data: EdgeDeteccionIn,
    _: None = Depends(require_edge_key),
):
    camara = camara_repo.get_camara(data.camara_id)
    if camara is None:
        raise HTTPException(status_code=404, detail="Cámara no encontrada.")

    zona_id = data.zona_config_id if data.zona_config_id is not None else camara[12]

    edge_repo.upsert_estado(
        camara_id=data.camara_id,
        zona_config_id=zona_id,
        personas=data.personas,
        nivel=data.nivel,
        alerta_activa=data.alerta,
        frame_evidencia_b64=data.frame_evidencia_b64,
    )

    if data.alerta:
        try:
            # sesion_id/usuario_id en NULL: esta alerta no viene de una
            # sesión de monitoreo iniciada desde el navegador, viene del
            # proceso que corre en la laptop del local.
            # Si la sesión del back-end local ya registró esta aglomeración
            # (el agente solo reenvía su resultado), se reutiliza esa alerta:
            # aquí solo se avisa a los usuarios conectados a esta instancia.
            db_alerta, _ = alerta_repo.crear_alerta_sin_duplicar(
                sesion_id=None,
                usuario_id=None,
                zona_config_id=zona_id,
                nivel=data.nivel if data.nivel in ("bajo", "medio", "alto") else "alto",
                personas=data.personas,
                camara_id=data.camara_id,
            )
            await alerta_manager.broadcast({
                "tipo": "alerta",
                "id": db_alerta[0],
                "sesion_id": None,
                "camara_id": data.camara_id,
                "camara_nombre": camara[1],
                "nivel": data.nivel,
                "personas": data.personas,
                "fecha_alerta": db_alerta[7].isoformat() if db_alerta[7] else None,
            })
        except Exception:
            logger.exception("Error al guardar/publicar alerta de edge (camara_id=%s)", data.camara_id)


# ── GET /estado — estado en vivo para el dashboard remoto ───────────────────

@router.get("/estado", response_model=EstadoCamarasOut)
def obtener_estado(_: dict = Depends(require_auth)):
    rows = edge_repo.list_estados()
    return {"camaras": [_row_estado(r) for r in rows]}


# ── GET /estado/{camara_id}/evidencia — foto de evidencia en base64 ─────────

@router.get("/estado/{camara_id}/evidencia")
def obtener_evidencia(camara_id: int, _: dict = Depends(require_auth)):
    rows = edge_repo.list_estados()
    fila = next((r for r in rows if r[0] == camara_id), None)
    if fila is None or fila[5] is None:
        raise HTTPException(status_code=404, detail="No hay evidencia para esta cámara.")
    return {"camara_id": camara_id, "frame_evidencia_b64": fila[5]}


# ── GET /local — sesiones de cámara de este mismo back-end ──────────────────

@router.get("/local")
def sesiones_locales(_: None = Depends(require_edge_key)):
    ahora = time.time()
    camaras = []
    for sesion_id, d in sesiones_de_camara():
        with d["lock"]:
            resultado, t, alerta_id = d.get("resultado"), d.get("t_resultado"), d.get("ultima_alerta_id")
        if not resultado or t is None or "personas" not in resultado:
            continue  # todavía sin un cuadro analizado: el agente sigue con lo suyo
        camaras.append({
            "camara_id": d["camara_id"],
            "sesion_id": sesion_id,
            "zona_config_id": d.get("zona_id"),
            "personas": resultado["personas"],
            "nivel": resultado.get("nivel", "sin_aglomeracion"),
            "edad_seg": round(ahora - t, 1),
            "ultima_alerta_id": alerta_id,
        })
    return {"camaras": camaras}


@router.get("/local/{camara_id}/foto-alerta")
def foto_alerta_local(camara_id: int, _: None = Depends(require_edge_key)):
    for _sid, d in sesiones_de_camara():
        if d["camara_id"] == camara_id:
            with d["lock"]:
                foto = d.get("frame_alerta")
            if foto:
                return Response(content=foto, media_type="image/jpeg")
    raise HTTPException(status_code=404, detail="Sin foto de alerta para esa cámara.")


# ── POST /local/alerta y PUT /local/alerta/{id}/clip — alertas del agente ────
# Cuando el agente analiza una cámara por su cuenta (nadie la tiene abierta en
# Multi-cámara), registra la alerta aquí primero: así suena en las pantallas
# conectadas a este back-end local, y el agente recibe el id para guardar el
# clip de 8 s con el mismo nombre que usan las sesiones locales.

_EVIDENCIAS = "uploads/evidencias"


class EdgeAlertaLocalIn(BaseModel):
    camara_id: int
    zona_config_id: int | None = None
    personas: int
    nivel: str = "alto"


class EdgeClipIn(BaseModel):
    archivo: str


@router.post("/local/alerta")
async def registrar_alerta_local(data: EdgeAlertaLocalIn, _: None = Depends(require_edge_key)):
    camara = camara_repo.get_camara(data.camara_id)
    if camara is None:
        raise HTTPException(status_code=404, detail="Cámara no encontrada.")
    zona_id = data.zona_config_id if data.zona_config_id is not None else camara[12]
    nivel = data.nivel if data.nivel in ("bajo", "medio", "alto") else "alto"
    fila, creada = alerta_repo.crear_alerta_sin_duplicar(
        sesion_id=None, usuario_id=None, zona_config_id=zona_id,
        nivel=nivel, personas=data.personas, camara_id=data.camara_id,
    )
    if creada:
        # Si se reutilizó una alerta de la sesión local, esta ya avisó.
        await alerta_manager.broadcast({
            "tipo": "alerta",
            "id": fila[0],
            "sesion_id": None,
            "camara_id": data.camara_id,
            "camara_nombre": camara[1],
            "nivel": nivel,
            "personas": data.personas,
            "fecha_alerta": fila[7].isoformat() if fila[7] else None,
        })
    return {"id": fila[0], "creada": creada, "tiene_clip": fila[10] is not None}


@router.put("/local/alerta/{alerta_id}/clip", status_code=204)
def adjuntar_clip_local(alerta_id: int, data: EdgeClipIn, _: None = Depends(require_edge_key)):
    # Solo el nombre que corresponde a esta alerta y dentro de la carpeta de
    # evidencias: el agente no puede apuntar el clip a otro archivo.
    if not re.fullmatch(rf"alerta_{alerta_id}\.(mp4|webm)", data.archivo):
        raise HTTPException(status_code=422, detail="Nombre de clip no válido.")
    ruta = f"{_EVIDENCIAS}/{data.archivo}"
    if not os.path.isfile(ruta):
        raise HTTPException(status_code=404, detail="El clip no existe en la carpeta de evidencias.")
    if alerta_repo.get_alerta(alerta_id) is None:
        raise HTTPException(status_code=404, detail="Alerta no encontrada.")
    alerta_repo.actualizar_clip(alerta_id, ruta)
