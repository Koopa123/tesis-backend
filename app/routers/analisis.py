import os
import shutil
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.config import Settings, get_settings
from app.core.security import require_auth
from app.models.schemas import AnalisisListOut, AnalisisUploadResponse
from app.repositories import analisis_repo, preset_repo
from detector.detector import generar_stream_video

router = APIRouter(prefix="/analisis", tags=["Análisis"])


@router.post("", response_model=AnalisisUploadResponse, status_code=202)
async def upload_video(
    preset_id: int = Form(...),
    file: UploadFile = File(...),
    _: dict = Depends(require_auth),
    settings: Settings = Depends(get_settings),
):
    """
    Sube el video al servidor y devuelve la URL del stream MJPEG.
    El frontend debe abrir esa URL como <img src="..."> para ver el análisis en vivo.
    """
    if not preset_repo.get_preset(preset_id):
        raise HTTPException(status_code=404, detail="Preset no encontrado")

    nombre_unico = f"{uuid.uuid4()}_{file.filename}"
    ruta = os.path.join(settings.videos_folder, nombre_unico)

    with open(ruta, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    stream_url = (
        f"/analisis/stream/{nombre_unico}"
        f"?preset_id={preset_id}&nombre_original={file.filename}"
    )
    return {
        "mensaje": "Video subido correctamente. Abre stream_url para ver el análisis.",
        "nombre_video": file.filename,
        "stream_url": stream_url,
    }


# Sin auth — flujo MJPEG que el browser abre como <img src>
@router.get("/stream/{nombre_video}", include_in_schema=False)
def stream_video(
    nombre_video: str,
    preset_id: int,
    nombre_original: str | None = None,
    settings: Settings = Depends(get_settings),
):
    preset = preset_repo.get_preset(preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail="Preset no encontrado")

    ruta = os.path.join(settings.videos_folder, nombre_video)
    if not os.path.exists(ruta):
        raise HTTPException(status_code=404, detail="Video no encontrado en servidor")

    return StreamingResponse(
        generar_stream_video(
            ruta,
            nombre_original or nombre_video,
            zonas=preset[3] or [],
            preset_id=preset_id,
            preset_nombre=preset[1],
        ),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.get("", response_model=AnalisisListOut)
def list_analisis(_: dict = Depends(require_auth)):
    """Historial de todos los análisis realizados, del más reciente al más antiguo."""
    datos = analisis_repo.list_analisis()
    return {
        "analisis": [
            {
                "id": f[0],
                "nombre_video": f[1],
                "personas_maximas": f[2],
                "grupo_mayor_maximo": f[3],
                "nivel_final": f[4],
                "fecha": f[5].isoformat() if f[5] else None,
                "preset_nombre": f[6],
            }
            for f in datos
        ]
    }
