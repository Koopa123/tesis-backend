"""Consulta del registro de auditoría. Solo administrador."""
from fastapi import APIRouter, Depends, Query

from app.core.security import require_admin
from app.models.schemas import RegistroAuditoriaOut
from app.repositories import auditoria_repo

router = APIRouter(prefix="/api/auditoria", tags=["Auditoría"])


@router.get("", response_model=list[RegistroAuditoriaOut])
def listar_auditoria(
    accion: str | None = Query(None, description="Filtrar por tipo de acción, p. ej. ver_clip"),
    usuario_id: int | None = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    _: dict = Depends(require_admin),
):
    return [
        {
            "id": r[0], "fecha": r[1], "usuario_id": r[2], "usuario_nombre": r[3],
            "accion": r[4], "recurso": r[5], "recurso_id": r[6], "detalle": r[7], "ip": r[8],
        }
        for r in auditoria_repo.listar(accion=accion, usuario_id=usuario_id, limit=limit)
    ]
