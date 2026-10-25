"""
Registro de auditoría: quién vio o descargó evidencias y quién cambió cuentas,
cámaras o zonas. Es la parte de "detección" de la prevención de pérdida de datos.

Registrar nunca debe tumbar la petición que audita: si la BD falla, solo se loguea.
"""
import logging
import threading
import time

from fastapi import Request

from app.repositories import auditoria_repo

logger = logging.getLogger(__name__)

# Una misma vista (mismo usuario, acción y recurso) se registra una sola vez
# cada VENTANA_VISTAS segundos: abrir el Historial carga todas las miniaturas
# y un MJPEG se reconecta varias veces, y eso llenaría el registro de ruido.
VENTANA_VISTAS = 600
_ultimas_vistas: dict[tuple, float] = {}
_vistas_lock = threading.Lock()


def _ip(request: Request | None) -> str | None:
    if request is None or request.client is None:
        return None
    return request.client.host


def auditar(
    request: Request | None,
    usuario: dict | int | None,
    accion: str,
    recurso: str | None = None,
    recurso_id: int | None = None,
    detalle: str | None = None,
) -> None:
    """`usuario` puede ser el payload del JWT, un id o None (acciones del sistema)."""
    if isinstance(usuario, dict):
        usuario_id = int(usuario["sub"]) if usuario.get("sub") is not None else None
    else:
        usuario_id = usuario
    try:
        auditoria_repo.registrar(usuario_id, accion, recurso, recurso_id, detalle, _ip(request))
    except Exception:
        logger.exception("No se pudo registrar la auditoría (%s %s %s)", accion, recurso, recurso_id)


def auditar_vista(request: Request | None, usuario: dict, accion: str, recurso: str, recurso_id: int) -> None:
    """Como auditar(), para ver imágenes o videos: no repite la misma vista dentro de VENTANA_VISTAS."""
    clave = (usuario.get("sub"), accion, recurso, recurso_id)
    ahora = time.monotonic()
    with _vistas_lock:
        if ahora - _ultimas_vistas.get(clave, -VENTANA_VISTAS) < VENTANA_VISTAS:
            return
        _ultimas_vistas[clave] = ahora
        if len(_ultimas_vistas) > 5000:   # no crecer sin límite
            for k in [k for k, t in _ultimas_vistas.items() if ahora - t >= VENTANA_VISTAS]:
                del _ultimas_vistas[k]
    auditar(request, usuario, accion, recurso, recurso_id)
