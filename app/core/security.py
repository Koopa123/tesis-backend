from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException
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
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")


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
