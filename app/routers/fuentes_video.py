from fastapi import APIRouter, Depends, HTTPException

from app.core.security import require_auth
from app.models.schemas import (
    CamaraOut,
    FuentesVideoOut,
    SeleccionFuenteOut,
    SeleccionFuenteRequest,
)
from app.repositories import camara_repo

router = APIRouter(prefix="/api/fuentes-video", tags=["Fuentes de Video"])

_FUENTES_FIJAS = [
    {
        "tipo": "webcam",
        "nombre": "Webcam del navegador",
        "disponible": True,
        "nota": "La webcam se captura desde el frontend.",
    },
    {
        "tipo": "grabacion_previa",
        "nombre": "Grabación previa",
        "disponible": True,
        "nota": None,
    },
    {
        "tipo": "camara_ip",
        "nombre": "Cámara IP registrada",
        "disponible": False,
        "nota": "Preparado para integración futura; no se conecta en el prototipo.",
    },
]


def _camara_row(c: tuple) -> dict:
    return {
        "id": c[0],
        "nombre": c[1],
        "direccion_ip": c[2],
        "ubicacion": c[3],
        "descripcion": c[4],
        "activa": c[5],
        "fecha_registro": c[6].isoformat() if c[6] else None,
    }


@router.get("", response_model=FuentesVideoOut)
def listar_fuentes(_: dict = Depends(require_auth)):
    """
    Devuelve las fuentes de video disponibles para el monitoreo junto con
    las cámaras IP registradas y activas.
    """
    camaras = camara_repo.list_camaras(solo_activas=True)
    return {
        "fuentes_disponibles": _FUENTES_FIJAS,
        "camaras_ip": [_camara_row(c) for c in camaras],
    }


@router.post("/seleccionar", response_model=SeleccionFuenteOut)
def seleccionar_fuente(
    data: SeleccionFuenteRequest,
    _: dict = Depends(require_auth),
):
    """
    Valida y confirma la selección de fuente de video.
    No inicia el monitoreo — para eso usar POST /api/monitoreo/iniciar.
    """
    if data.tipo == "camara_ip":
        if not data.camara_id:
            raise HTTPException(
                status_code=422,
                detail="Debes indicar camara_id al seleccionar tipo camara_ip.",
            )
        camara = camara_repo.get_camara(data.camara_id)
        if not camara:
            raise HTTPException(status_code=404, detail="Cámara no encontrada.")
        return {
            "tipo": data.tipo,
            "camara_id": data.camara_id,
            "grabacion_id": None,
            "mensaje": (
                f"Cámara IP '{camara[1]}' seleccionada. "
                "La conexión real queda preparada para integración futura."
            ),
        }

    if data.tipo == "grabacion_previa":
        return {
            "tipo": data.tipo,
            "camara_id": None,
            "grabacion_id": data.grabacion_id,
            "mensaje": "Grabación previa seleccionada. Inicia el monitoreo para comenzar.",
        }

    return {
        "tipo": "webcam",
        "camara_id": None,
        "grabacion_id": None,
        "mensaje": "Webcam seleccionada. El video será capturado por el navegador.",
    }
