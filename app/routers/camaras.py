from fastapi import APIRouter, Depends, HTTPException

from app.core.security import require_admin, require_auth
from app.models.schemas import CamaraCreate, CamaraEstadoUpdate, CamaraOut
from app.repositories import camara_repo

router = APIRouter(prefix="/api/camaras", tags=["Cámaras IP"])


def _row(c: tuple) -> dict:
    return {
        "id": c[0],
        "nombre": c[1],
        "direccion_ip": c[2],
        "ubicacion": c[3],
        "descripcion": c[4],
        "activa": c[5],
        "fecha_registro": c[6].isoformat() if c[6] else None,
    }


@router.post("", response_model=CamaraOut, status_code=201)
def registrar_camara(
    data: CamaraCreate,
    _: dict = Depends(require_admin),
):
    """Registra una cámara IP. Solo guarda la configuración, no verifica conectividad."""
    camara = camara_repo.create_camara(
        nombre=data.nombre,
        direccion_ip=data.direccion_ip,
        ubicacion=data.ubicacion,
        descripcion=data.descripcion,
        activa=data.activa,
    )
    return _row(camara)


@router.get("", response_model=list[CamaraOut])
def listar_camaras(_: dict = Depends(require_auth)):
    """Lista todas las cámaras registradas. Accesible por cualquier usuario autenticado."""
    return [_row(c) for c in camara_repo.list_camaras()]


@router.patch("/{camara_id}/estado", response_model=CamaraOut)
def actualizar_estado(
    camara_id: int,
    data: CamaraEstadoUpdate,
    _: dict = Depends(require_admin),
):
    """Activa o desactiva una cámara. Solo administrador."""
    camara = camara_repo.update_estado(camara_id, data.activa)
    if not camara:
        raise HTTPException(status_code=404, detail="Cámara no encontrada")
    return _row(camara)


@router.delete("/{camara_id}", status_code=204)
def eliminar_camara(
    camara_id: int,
    _: dict = Depends(require_admin),
):
    """Elimina una cámara registrada. Solo administrador."""
    if not camara_repo.get_camara(camara_id):
        raise HTTPException(status_code=404, detail="Cámara no encontrada")
    camara_repo.delete_camara(camara_id)
