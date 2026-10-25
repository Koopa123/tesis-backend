"""
Evidencias y tickets de medios (prevención de pérdida de datos).

Antes las fotos y los clips se servían por la carpeta pública /uploads, sin
sesión y con nombres numerados (sesion_{id}.jpg, alerta_{id}.mp4): cambiando el
número se podía ver la evidencia de cualquier alerta. Ahora:

GET  /api/media/evidencia/resultado/{id} → foto de mayor concentración (con sesión)
GET  /api/media/evidencia/alerta/{id}    → clip de la alerta (con sesión)
POST /api/media/ticket                   → ticket corto para <img>/<video>

Cada consulta de evidencia queda en la auditoría.
"""
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from app.config import Settings, get_settings
from app.core.auditoria import auditar_vista
from app.core.security import create_media_ticket, require_auth
from app.models.schemas import TicketMediaOut, TicketMediaRequest
from app.repositories import alerta_repo, analisis_repo, grabacion_repo, monitoreo_repo

router = APIRouter(prefix="/api/media", tags=["Evidencias"])

_CARPETA = os.path.realpath("uploads/evidencias")
_SIN_CACHE = {"Cache-Control": "no-store, private"}


def _archivo_evidencia(ruta: str | None) -> str:
    """Ruta real del archivo, solo si está dentro de uploads/evidencias."""
    if not ruta:
        raise HTTPException(status_code=404, detail="Esta evidencia no existe o ya fue eliminada.")
    real = os.path.realpath(ruta)
    if os.path.commonpath([real, _CARPETA]) != _CARPETA:
        raise HTTPException(status_code=404, detail="Evidencia no encontrada.")
    if not os.path.isfile(real):
        raise HTTPException(
            status_code=404,
            detail="El archivo de evidencia está en el equipo del local, no en este servidor.",
        )
    return real


@router.get("/evidencia/resultado/{resultado_id}")
def evidencia_resultado(resultado_id: int, request: Request, payload: dict = Depends(require_auth)):
    """Foto de mayor concentración de una sesión. Las de cámara las ve el equipo;
    las de una grabación, su dueño o un administrador (igual que el historial)."""
    fila = analisis_repo.get_evidencia(resultado_id)
    if fila is None:
        raise HTTPException(status_code=404, detail="Resultado no encontrado.")
    ruta, tipo_fuente, dueno = fila
    if (tipo_fuente != "camara_ip" and payload.get("rol") != "administrador"
            and dueno != int(payload["sub"])):
        raise HTTPException(status_code=403, detail="No tienes acceso a esta evidencia.")
    real = _archivo_evidencia(ruta)
    auditar_vista(request, payload, "ver_evidencia", "resultado", resultado_id)
    return FileResponse(real, media_type="image/jpeg", headers=_SIN_CACHE)


@router.get("/evidencia/alerta/{alerta_id}")
def evidencia_alerta(alerta_id: int, request: Request, payload: dict = Depends(require_auth)):
    """Clip de una alerta. Las alertas son del equipo de seguridad: lo ve cualquier usuario con sesión."""
    fila = alerta_repo.get_alerta(alerta_id)
    if fila is None:
        raise HTTPException(status_code=404, detail="Alerta no encontrada.")
    real = _archivo_evidencia(fila[11])   # 11 = clip_evidencia en _COLS_JOIN
    auditar_vista(request, payload, "ver_clip", "alerta", alerta_id)
    tipo = "video/webm" if real.lower().endswith(".webm") else "video/mp4"
    return FileResponse(real, media_type=tipo, headers=_SIN_CACHE)


@router.post("/ticket", response_model=TicketMediaOut)
def emitir_ticket(
    data: TicketMediaRequest,
    payload: dict = Depends(require_auth),
    settings: Settings = Depends(get_settings),
):
    """
    Ticket para poner en la URL de un <img> (MJPEG de una cámara) o un <video>
    (archivo de una grabación), que no pueden mandar el header Authorization.
    Vale solo para ese recurso y por poco tiempo; no sirve como sesión.
    """
    if data.recurso == "mjpeg":
        sesion = monitoreo_repo.get_sesion(data.id)
        if sesion is None or sesion[2] != "camara_ip":
            raise HTTPException(status_code=404, detail="Sesión de cámara no encontrada.")
        segundos = settings.media_ticket_segundos
    else:
        grabacion = grabacion_repo.get_grabacion(data.id)
        if grabacion is None:
            raise HTTPException(status_code=404, detail="Grabación no encontrada.")
        if grabacion[5] != int(payload["sub"]) and payload.get("rol") != "administrador":
            raise HTTPException(status_code=403, detail="Sin acceso a esta grabación.")
        segundos = settings.media_ticket_grabacion_segundos
    ticket = create_media_ticket(payload, data.recurso, data.id, segundos, settings)
    return {"ticket": ticket, "expira_en_segundos": segundos}
