import os
import shutil
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from app.config import Settings, get_settings
from app.core.security import decode_token, require_auth
from app.models.schemas import GrabacionOut, GrabacionesListOut
from app.repositories import grabacion_repo

router = APIRouter(prefix="/api/grabaciones", tags=["Grabaciones"])

_EXTENSIONES = {".mp4", ".avi", ".mov", ".mkv"}


def _row(g: tuple) -> dict:
    # índices: 0=id, 1=nombre_archivo, 2=ruta_archivo, 3=tipo_contenido,
    #          4=tamanio_bytes, 5=usuario_id, 6=fecha_carga, 7=fecha_grabacion
    return {
        "id": g[0],
        "nombre_archivo": g[1],
        "ruta_archivo": g[2],
        "tipo_contenido": g[3],
        "tamanio_bytes": g[4],
        "usuario_id": g[5],
        "fecha_carga": g[6].isoformat() if g[6] else None,
        "fecha_grabacion": g[7].isoformat() if g[7] else None,
    }


@router.post("", response_model=GrabacionOut, status_code=201)
async def cargar_grabacion(
    file: UploadFile = File(...),
    fecha_grabacion: str | None = Form(None, description="ISO 8601: 2025-06-15T14:30"),
    payload: dict = Depends(require_auth),
    settings: Settings = Depends(get_settings),
):
    """
    Sube una grabación de video al servidor.
    El campo fecha_grabacion (opcional) indica cuándo fue filmado el video.
    Extensiones: .mp4, .avi, .mov, .mkv
    """
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in _EXTENSIONES:
        raise HTTPException(
            status_code=422,
            detail=f"Extensión no permitida. Usa: {', '.join(sorted(_EXTENSIONES))}",
        )

    nombre_unico = f"{uuid.uuid4()}{ext}"
    ruta = os.path.join(settings.grabaciones_folder, nombre_unico)

    with open(ruta, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    grabacion = grabacion_repo.create_grabacion(
        nombre_archivo=file.filename or nombre_unico,
        ruta_archivo=ruta,
        tipo_contenido=file.content_type,
        tamanio_bytes=os.path.getsize(ruta),
        usuario_id=int(payload["sub"]),
        fecha_grabacion=fecha_grabacion or None,
    )
    return _row(grabacion)


@router.get("/{grabacion_id}/file")
def servir_grabacion(
    grabacion_id: int,
    token: str = Query(..., description="JWT Bearer token como query param"),
):
    """
    Sirve el archivo de video para reproducción en el navegador.
    Acepta el token como query param porque <video> no soporta headers personalizados.
    """
    try:
        payload = decode_token(token)
    except HTTPException:
        raise HTTPException(status_code=401, detail="Token inválido.")

    grabacion = grabacion_repo.get_grabacion(grabacion_id)
    if grabacion is None:
        raise HTTPException(status_code=404, detail="Grabación no encontrada.")

    usuario_id = int(payload["sub"])
    rol = payload.get("rol", "")
    if grabacion[5] != usuario_id and rol != "administrador":
        raise HTTPException(status_code=403, detail="Sin acceso a esta grabación.")

    ruta = grabacion[2]
    if not os.path.exists(ruta):
        raise HTTPException(status_code=404, detail="Archivo no encontrado en disco.")

    return FileResponse(
        ruta,
        media_type=grabacion[3] or "video/mp4",
        filename=grabacion[1],
    )


@router.get("", response_model=GrabacionesListOut)
def listar_grabaciones(payload: dict = Depends(require_auth)):
    """
    Lista grabaciones.
    - Administrador: ve todas.
    - Vigilante: ve solo las propias.
    """
    es_admin = payload.get("rol") == "administrador"
    usuario_id = int(payload["sub"])
    grabaciones = grabacion_repo.list_grabaciones(
        usuario_id=None if es_admin else usuario_id
    )
    return {"grabaciones": [_row(g) for g in grabaciones]}
