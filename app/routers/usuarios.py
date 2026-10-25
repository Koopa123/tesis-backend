"""
Gestión de cuentas de usuario, solo para el administrador.

Las cuentas creadas desde el registro público quedan desactivadas (ver auth.py):
aquí el administrador las activa o las rechaza, y puede desactivar a quien ya
no deba entrar al sistema.
"""
from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.auditoria import auditar
from app.core.security import require_admin
from app.models.schemas import EstadoUsuarioRequest, UsuarioAdminOut
from app.repositories import user_repo

router = APIRouter(prefix="/api/usuarios", tags=["Usuarios"])


def _row(r: tuple) -> dict:
    return {"id": r[0], "nombre": r[1], "email": r[2], "rol": r[3], "activo": r[4], "fecha_creacion": r[5]}


@router.get("", response_model=list[UsuarioAdminOut])
def listar_usuarios(_: dict = Depends(require_admin)):
    """Todas las cuentas; las pendientes de activación aparecen primero."""
    return [_row(r) for r in user_repo.list_users()]


@router.patch("/{usuario_id}/estado", response_model=UsuarioAdminOut)
def cambiar_estado(usuario_id: int, data: EstadoUsuarioRequest, request: Request, payload: dict = Depends(require_admin)):
    """Activa o desactiva una cuenta. Nadie puede desactivarse a sí mismo ni dejar el sistema sin administradores."""
    if usuario_id == int(payload["sub"]):
        raise HTTPException(status_code=400, detail="No puedes cambiar el estado de tu propia cuenta.")
    usuario = user_repo.get_user_any(usuario_id)
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if not data.activo and usuario[3] == "administrador" and usuario[4] and user_repo.count_active_admins() <= 1:
        raise HTTPException(status_code=400, detail="Debe quedar al menos un administrador activo.")
    actualizado = user_repo.set_active(usuario_id, data.activo)
    auditar(request, payload, "activar_usuario" if data.activo else "desactivar_usuario", "usuario", usuario_id, usuario[1])
    return _row(actualizado)


@router.delete("/{usuario_id}", status_code=204)
def rechazar_usuario(usuario_id: int, request: Request, payload: dict = Depends(require_admin)):
    """Elimina una cuenta desactivada que nunca se usó (típicamente, un registro rechazado)."""
    if usuario_id == int(payload["sub"]):
        raise HTTPException(status_code=400, detail="No puedes eliminar tu propia cuenta.")
    usuario = user_repo.get_user_any(usuario_id)
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if usuario[4]:
        raise HTTPException(status_code=409, detail="Solo se pueden eliminar cuentas desactivadas. Desactívala primero.")
    if user_repo.has_records(usuario_id):
        raise HTTPException(
            status_code=409,
            detail="La cuenta tiene registros en el sistema; déjala desactivada para conservar su historial.",
        )
    user_repo.delete_user(usuario_id)
    auditar(request, payload, "rechazar_usuario", "usuario", usuario_id, usuario[1])
