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
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

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
            db_alerta = alerta_repo.crear_alerta(
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
