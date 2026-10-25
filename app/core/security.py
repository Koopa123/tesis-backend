from datetime import datetime, timedelta, timezone

from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import Settings, get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer()


# ── Contraseñas ──────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ── Tokens JWT ───────────────────────────────────────────────────────────────

def create_token(user_id: int, email: str, rol: str, settings: Settings = None) -> str:
    if settings is None:
        settings = get_settings()
    payload = {
        "sub": str(user_id),
        "email": email,
        "rol": rol,
        "exp": datetime.now(tz=timezone.utc) + timedelta(hours=settings.jwt_expire_hours),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str, settings: Settings = None) -> dict:
    if settings is None:
        settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")
    # Un ticket de medios solo abre el video para el que se emitió: no sirve
    # como token de sesión para el resto de la API.
    if payload.get("typ") == "media":
        raise HTTPException(status_code=401, detail="Token inválido o expirado")
    return payload


# ── Tickets de medios ────────────────────────────────────────────────────────
# <img> y <video> no pueden enviar el header Authorization, así que antes se
# ponía el JWT de sesión (24 h, válido para toda la API) en la URL, donde queda
# en el historial del navegador y en los registros del servidor. Ahora la URL
# lleva un ticket que vale para UN recurso y por poco tiempo.

def create_media_ticket(payload: dict, recurso: str, recurso_id: int, segundos: int,
                        settings: Settings = None) -> str:
    if settings is None:
        settings = get_settings()
    claims = {
        "sub": payload["sub"],
        "rol": payload.get("rol"),
        "typ": "media",
        "rec": recurso,
        "rid": recurso_id,
        "exp": datetime.now(tz=timezone.utc) + timedelta(seconds=segundos),
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_media_ticket(ticket: str, recurso: str, recurso_id: int, settings: Settings = None) -> dict:
    """Valida el ticket y que sea para este recurso; devuelve sus claims (sub, rol)."""
    if settings is None:
        settings = get_settings()
    try:
        claims = jwt.decode(ticket, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        raise HTTPException(status_code=401, detail="Ticket inválido o expirado")
    if claims.get("typ") != "media" or claims.get("rec") != recurso or claims.get("rid") != recurso_id:
        raise HTTPException(status_code=401, detail="Ticket inválido o expirado")
    return claims


# ── Dependencies de FastAPI ──────────────────────────────────────────────────

def require_auth(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Valida el Bearer token y devuelve el payload decodificado."""
    return decode_token(credentials.credentials, settings)


def require_role(*allowed_roles: str):
    """
    Factory que devuelve una dependency que verifica el rol del usuario.

    Uso:
        _: dict = Depends(require_role("administrador"))
        _: dict = Depends(require_role("administrador", "vigilante"))
    """
    def _check(payload: dict = Depends(require_auth)) -> dict:
        if payload.get("rol") not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail="No tienes permiso para realizar esta acción",
            )
        return payload
    return _check


# Atajo para endpoints exclusivos del administrador
require_admin = require_role("administrador")


# ── Autenticación del edge (laptop en el local) ──────────────────────────────

def require_edge_key(
    x_edge_api_key: str = Header(..., alias="X-Edge-Api-Key"),
    settings: Settings = Depends(get_settings),
) -> None:
    """
    Valida la clave compartida que usa la laptop del local para reportar
    detecciones. No es un JWT de usuario: es una clave fija de dispositivo,
    porque del lado del edge no hay una persona logueada en un navegador.
    """
    if not settings.edge_api_key or x_edge_api_key != settings.edge_api_key:
        raise HTTPException(status_code=401, detail="Clave de edge inválida.")
