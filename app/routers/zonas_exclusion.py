import json
import os
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from pydantic import ValidationError

from app.core.auditoria import auditar
from app.core.security import require_admin, require_auth
from app.models.schemas import ZonaExclusionOut, ZonaRect, ZonasExclusionListOut
from app.repositories import zona_exclusion_repo

router = APIRouter(prefix="/api/zonas-exclusion", tags=["Zonas de exclusión"])

_MIME_FRAME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
_EXTENSIONES_FRAME = set(_MIME_FRAME)
_MAX_FRAME_BYTES = 5 * 1024 * 1024
_RUTA_FRAME = "api/zonas-exclusion/frame"


def _row(r: tuple) -> dict:
    # índices: 0=id, 1=nombre, 2=frame_referencia, 3=zonas,
    #          4=umbral_medio, 5=umbral_alto, 6=ventana_segundos, 7=cooldown_segundos,
    #          8=creado_por, 9=activa, 10=fecha_creacion, 11=fecha_actualizacion
    return {
        "id": r[0],
        "nombre": r[1],
        "frame_referencia": r[2],
        "zonas": r[3],
        "umbral_medio": r[4],
        "umbral_alto": r[5],
        "ventana_segundos": float(r[6]),
        "cooldown_segundos": r[7],
        "creado_por": r[8],
        "activa": r[9],
        "fecha_creacion": r[10].isoformat() if r[10] else None,
        "fecha_actualizacion": r[11].isoformat() if r[11] else None,
    }


def _parse_zonas(zonas_json: str) -> list[dict]:
    try:
        data = json.loads(zonas_json)
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="El campo 'zonas' no es JSON válido.")
    if not isinstance(data, list):
        raise HTTPException(status_code=422, detail="El campo 'zonas' debe ser una lista.")
    # Lista vacía es válida: esta configuración también sirve solo para
    # personalizar umbrales (medio/alto/ventana/cooldown) sin excluir
    # ninguna área del conteo de personas.
    resultado = []
    for i, rect in enumerate(data):
        try:
            resultado.append(ZonaRect.model_validate(rect).model_dump())
        except ValidationError as exc:
            msg = exc.errors()[0]["msg"]
            raise HTTPException(status_code=422, detail=f"Rectángulo #{i}: {msg}")
    return resultado


def _leer_frame(file: UploadFile) -> tuple[str, bytes, str]:
    """
    Lee la imagen de referencia para guardarla en la BD, no en disco: Railway
    no tiene volumen persistente (borra uploads/ en cada redespliegue) y la
    laptop del local y la nube no comparten disco, pero sí la misma BD.
    Devuelve (frame_referencia, bytes, mime). frame_referencia es la ruta
    relativa del endpoint que la sirve, así el frontend la arma igual que antes.
    """
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in _EXTENSIONES_FRAME:
        raise HTTPException(
            status_code=422,
            detail=f"Extensión no permitida para frame. Usa: {', '.join(sorted(_EXTENSIONES_FRAME))}",
        )
    datos = file.file.read(_MAX_FRAME_BYTES + 1)
    if len(datos) > _MAX_FRAME_BYTES:
        raise HTTPException(status_code=413, detail="La imagen de referencia supera los 5 MB.")
    return f"{_RUTA_FRAME}/{uuid.uuid4()}{ext}", datos, _MIME_FRAME[ext]


@router.post("", response_model=ZonaExclusionOut, status_code=201)
async def crear_zona(
    request: Request,
    nombre: str = Form(..., min_length=1, max_length=120),
    frame: UploadFile = File(...),
    zonas: str = Form(..., description="Lista JSON de rectángulos normalizados"),
    umbral_medio: int = Form(4, ge=1, description="Personas mínimas para nivel Medio"),
    umbral_alto: int = Form(6, ge=1, description="Personas mínimas para nivel Alto"),
    ventana_segundos: float = Form(2.0, ge=0.5, description="Duración ventana deslizante (s)"),
    cooldown_segundos: int = Form(10, ge=1, description="Pausa mínima entre alertas (s)"),
    payload: dict = Depends(require_admin),
):
    if umbral_alto <= umbral_medio:
        raise HTTPException(
            status_code=422,
            detail="umbral_alto debe ser mayor que umbral_medio.",
        )
    zonas_list = _parse_zonas(zonas)
    ruta_frame, frame_bytes, frame_mime = _leer_frame(frame)
    row = zona_exclusion_repo.create_zona(
        nombre=nombre.strip(),
        frame_referencia=ruta_frame,
        frame_imagen=frame_bytes,
        frame_mime=frame_mime,
        zonas=zonas_list,
        creado_por=int(payload["sub"]),
        umbral_medio=umbral_medio,
        umbral_alto=umbral_alto,
        ventana_segundos=ventana_segundos,
        cooldown_segundos=cooldown_segundos,
    )
    auditar(request, payload, "crear_zona", "zona", row[0], nombre.strip())
    return _row(row)


@router.get("", response_model=ZonasExclusionListOut)
def listar_zonas(payload: dict = Depends(require_auth)):
    # Lectura abierta a todo usuario autenticado: el vigilante elige una zona
    # para su análisis en Monitoreo. Crear, editar y borrar sigue siendo de admin.
    rows = zona_exclusion_repo.list_zonas()
    return {"configuraciones": [_row(r) for r in rows]}


@router.get("/frame/{nombre}")
def obtener_frame(nombre: str):
    # Sin token, igual que antes con /uploads/frames: la usa un <img>, que no
    # puede mandar el header Authorization. El nombre es un UUID, no adivinable.
    frame = zona_exclusion_repo.get_frame(f"{_RUTA_FRAME}/{nombre}")
    if frame is None:
        raise HTTPException(status_code=404, detail="Imagen no encontrada.")
    datos, mime = frame
    return Response(
        content=bytes(datos),
        media_type=mime,
        # El nombre cambia con cada imagen nueva, así que se puede cachear.
        headers={"Cache-Control": "private, max-age=86400, immutable"},
    )


@router.get("/{zona_id}", response_model=ZonaExclusionOut)
def obtener_zona(zona_id: int, payload: dict = Depends(require_auth)):
    row = zona_exclusion_repo.get_zona(zona_id)
    if row is None or not row[9]:   # row[9] = activa
        raise HTTPException(status_code=404, detail="Configuración no encontrada.")
    return _row(row)


@router.put("/{zona_id}", response_model=ZonaExclusionOut)
async def actualizar_zona(
    zona_id: int,
    request: Request,
    nombre: str | None = Form(None),
    frame: UploadFile | None = File(None),
    zonas: str | None = Form(None),
    umbral_medio: int | None = Form(None, ge=1),
    umbral_alto: int | None = Form(None, ge=1),
    ventana_segundos: float | None = Form(None, ge=0.5),
    cooldown_segundos: int | None = Form(None, ge=1),
    payload: dict = Depends(require_admin),
):
    existing = zona_exclusion_repo.get_zona(zona_id)
    if existing is None or not existing[9]:
        raise HTTPException(status_code=404, detail="Configuración no encontrada.")

    if umbral_medio is not None and umbral_alto is not None and umbral_alto <= umbral_medio:
        raise HTTPException(status_code=422, detail="umbral_alto debe ser mayor que umbral_medio.")

    nombre_val = nombre.strip() if nombre else None
    zonas_val = _parse_zonas(zonas) if zonas else None
    frame_val = frame_bytes = frame_mime = None
    if frame and frame.filename:
        frame_val, frame_bytes, frame_mime = _leer_frame(frame)

    campos = [nombre_val, zonas_val, frame_val, umbral_medio, umbral_alto, ventana_segundos, cooldown_segundos]
    if all(v is None for v in campos):
        raise HTTPException(status_code=422, detail="Envía al menos un campo para actualizar.")

    row = zona_exclusion_repo.update_zona(
        zona_id=zona_id,
        nombre=nombre_val,
        frame_referencia=frame_val,
        frame_imagen=frame_bytes,
        frame_mime=frame_mime,
        zonas=zonas_val,
        umbral_medio=umbral_medio,
        umbral_alto=umbral_alto,
        ventana_segundos=ventana_segundos,
        cooldown_segundos=cooldown_segundos,
    )
    auditar(request, payload, "editar_zona", "zona", zona_id, existing[1])
    return _row(row)


@router.delete("/{zona_id}")
def eliminar_zona(zona_id: int, request: Request, payload: dict = Depends(require_admin)):
    existing = zona_exclusion_repo.get_zona(zona_id)
    if existing is None or not existing[9]:
        raise HTTPException(status_code=404, detail="Configuración no encontrada.")
    zona_exclusion_repo.delete_zona(zona_id)
    auditar(request, payload, "eliminar_zona", "zona", zona_id, existing[1])
    return {"message": "Configuración de zonas eliminada correctamente."}
