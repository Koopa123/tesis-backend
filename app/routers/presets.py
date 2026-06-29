import os
import shutil
import uuid

import cv2
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.config import Settings, get_settings
from app.core.security import require_auth
from app.models.schemas import PresetOut, PresetsListOut, ZonasRequest
from app.repositories import preset_repo

router = APIRouter(prefix="/presets", tags=["Presets"])


def _preset_to_dict(p: tuple, settings: Settings) -> dict:
    """Convierte una fila de BD en el dict de respuesta."""
    return {
        "id": p[0],
        "nombre": p[1],
        "frame_url": f"/presets/{p[0]}/frame",
        "zonas": p[3] if p[3] is not None else [],
        "fecha_creacion": p[4].isoformat() if p[4] else None,
    }


@router.post("", response_model=PresetOut, status_code=201)
async def create_preset(
    nombre: str = Form(..., min_length=1, max_length=100),
    file: UploadFile = File(...),
    _: dict = Depends(require_auth),
    settings: Settings = Depends(get_settings),
):
    """
    Crea un preset: extrae el primer frame del video subido,
    lo guarda en disco y registra el preset en BD.
    """
    preset_uuid = str(uuid.uuid4())
    temp_path = os.path.join(settings.videos_folder, f"ref_{preset_uuid}.mp4")
    frame_name = f"frame_{preset_uuid}.jpg"
    frame_path = os.path.join(settings.frames_folder, frame_name)

    # Guardar video temporalmente
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Extraer primer frame
    cap = cv2.VideoCapture(temp_path)
    ret, frame = cap.read()
    cap.release()
    os.remove(temp_path)

    if not ret:
        raise HTTPException(status_code=422, detail="No se pudo extraer el primer frame del video")

    cv2.imwrite(frame_path, frame)

    try:
        preset_id = preset_repo.create_preset(nombre, frame_name, [])
    except Exception as e:
        if os.path.exists(frame_path):
            os.remove(frame_path)
        raise HTTPException(status_code=400, detail=f"Error al crear preset: {e}")

    return {
        "id": preset_id,
        "nombre": nombre,
        "frame_url": f"/presets/{preset_id}/frame",
        "zonas": [],
        "fecha_creacion": None,
    }


@router.get("", response_model=PresetsListOut)
def list_presets(
    _: dict = Depends(require_auth),
    settings: Settings = Depends(get_settings),
):
    presets = preset_repo.list_presets()
    return {"presets": [_preset_to_dict(p, settings) for p in presets]}


@router.get("/{preset_id}", response_model=PresetOut)
def get_preset(
    preset_id: int,
    _: dict = Depends(require_auth),
    settings: Settings = Depends(get_settings),
):
    preset = preset_repo.get_preset(preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail="Preset no encontrado")
    return _preset_to_dict(preset, settings)


@router.put("/{preset_id}/zonas")
def update_zones(
    preset_id: int,
    data: ZonasRequest,
    _: dict = Depends(require_auth),
):
    if not preset_repo.get_preset(preset_id):
        raise HTTPException(status_code=404, detail="Preset no encontrado")
    preset_repo.update_preset_zones(preset_id, data.zonas)
    return {"mensaje": "Zonas actualizadas", "zonas": data.zonas}


@router.delete("/{preset_id}", status_code=204)
def delete_preset(
    preset_id: int,
    _: dict = Depends(require_auth),
    settings: Settings = Depends(get_settings),
):
    preset = preset_repo.get_preset(preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail="Preset no encontrado")

    frame_path = os.path.join(settings.frames_folder, preset[2])
    if os.path.exists(frame_path):
        os.remove(frame_path)

    preset_repo.delete_preset(preset_id)


# Sin auth — se carga como <img src="..."> y los browsers no envían headers
@router.get("/{preset_id}/frame", include_in_schema=False)
def get_frame(
    preset_id: int,
    settings: Settings = Depends(get_settings),
):
    preset = preset_repo.get_preset(preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail="Preset no encontrado")

    frame_path = os.path.join(settings.frames_folder, preset[2])
    if not os.path.exists(frame_path):
        raise HTTPException(status_code=404, detail="Frame no encontrado en disco")

    return FileResponse(frame_path, media_type="image/jpeg")
