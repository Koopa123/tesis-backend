import logging
import threading
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, HTTPException, Request
from psycopg2.errors import UniqueViolation

from app.core.security import create_token, hash_password, require_auth, verify_password
from app.models.schemas import AuthResponse, LoginRequest, RegisterRequest, UserOut
from app.repositories import user_repo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Autenticación"])

# Límite de intentos fallidos de login, en memoria (un solo proceso de uvicorn).
# Se cuenta por IP y por email para frenar la fuerza bruta sobre una cuenta.
MAX_INTENTOS_FALLIDOS = 5
VENTANA_SEGUNDOS = 60
_fallidos: dict[str, deque] = defaultdict(deque)
_fallidos_lock = threading.Lock()


def _claves_login(request: Request, email: str) -> list[str]:
    ip = request.client.host if request.client else "desconocida"
    return [f"ip:{ip}", f"email:{email.strip().lower()}"]


def _bloqueado(claves: list[str]) -> bool:
    limite = time.monotonic() - VENTANA_SEGUNDOS
    with _fallidos_lock:
        for clave in claves:
            intentos = _fallidos[clave]
            while intentos and intentos[0] < limite:
                intentos.popleft()
            if len(intentos) >= MAX_INTENTOS_FALLIDOS:
                return True
    return False


def _registrar_fallido(claves: list[str]) -> None:
    ahora = time.monotonic()
    with _fallidos_lock:
        for clave in claves:
            _fallidos[clave].append(ahora)


@router.post("/registro", status_code=201)
def registro(data: RegisterRequest):
    """
    Crea una cuenta nueva con rol 'vigilante' (único rol permitido en registro público).
    La cuenta queda desactivada hasta que un administrador la active, así que no
    se devuelve token: cualquiera puede registrarse desde la web pública.
    El email debe ser único; si ya existe devuelve 409.
    """
    password_hash = hash_password(data.password)

    try:
        user_repo.create_user(
            nombre=data.nombre,
            email=data.email,
            password_hash=password_hash,
            rol="vigilante",
            activo=False,
        )
    except UniqueViolation:
        raise HTTPException(status_code=409, detail="Ese email ya está registrado")
    except Exception:
        # El detalle va solo al log: devolverlo al cliente expondría mensajes
        # internos de la base de datos.
        logger.exception("Error inesperado al registrar un usuario")
        raise HTTPException(status_code=500, detail="No se pudo crear la cuenta. Intenta de nuevo más tarde.")

    return {"mensaje": "Cuenta creada. Un administrador debe activarla antes de que puedas iniciar sesión."}


@router.post("/login", response_model=AuthResponse)
def login(data: LoginRequest, request: Request):
    """
    Autentica con email + contraseña. Retorna el token JWT con rol incluido.
    El mensaje de error es genérico a propósito (no revelar qué campo falla).
    """
    claves = _claves_login(request, data.email)
    if _bloqueado(claves):
        raise HTTPException(
            status_code=429,
            detail="Demasiados intentos fallidos. Espera un minuto e inténtalo de nuevo.",
        )

    usuario = user_repo.get_user_by_email(data.email)

    # Mismo mensaje para email inexistente, contraseña incorrecta o cuenta sin activar
    if not usuario or not verify_password(data.password, usuario[3]):
        _registrar_fallido(claves)
        raise HTTPException(status_code=401, detail="Email o contraseña incorrectos")

    user_id, nombre, email, _hash, rol = usuario
    token = create_token(user_id, email, rol)
    return {
        "token": token,
        "usuario": {"id": user_id, "nombre": nombre, "email": email, "rol": rol},
    }


@router.get("/me", response_model=UserOut)
def me(payload: dict = Depends(require_auth)):
    """
    Valida el token y devuelve los datos actuales del usuario desde la BD.
    El frontend puede llamar esto al iniciar para verificar si la sesión sigue activa.
    """
    user_id = int(payload["sub"])
    usuario = user_repo.get_user_by_id(user_id)

    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    db_id, nombre, email, rol = usuario
    return {"id": db_id, "nombre": nombre, "email": email, "rol": rol}
