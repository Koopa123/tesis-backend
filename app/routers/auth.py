from fastapi import APIRouter, Depends, HTTPException
from psycopg2.errors import UniqueViolation

from app.core.security import create_token, hash_password, require_auth, verify_password
from app.models.schemas import AuthResponse, LoginRequest, RegisterRequest, UserOut
from app.repositories import user_repo

router = APIRouter(prefix="/auth", tags=["Autenticación"])


@router.post("/registro", response_model=AuthResponse, status_code=201)
def registro(data: RegisterRequest):
    """
    Crea una cuenta nueva con rol 'vigilante' (único rol permitido en registro público).
    Retorna el token JWT listo para usar.
    El email debe ser único; si ya existe devuelve 409.
    """
    password_hash = hash_password(data.password)

    try:
        usuario = user_repo.create_user(
            nombre=data.nombre,
            email=data.email,
            password_hash=password_hash,
            rol="vigilante",
        )
    except UniqueViolation:
        raise HTTPException(status_code=409, detail="Ese email ya está registrado")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno al crear usuario: {e}")

    user_id, nombre, email, rol = usuario
    token = create_token(user_id, email, rol)
    return {
        "token": token,
        "usuario": {"id": user_id, "nombre": nombre, "email": email, "rol": rol},
    }


@router.post("/login", response_model=AuthResponse)
def login(data: LoginRequest):
    """
    Autentica con email + contraseña. Retorna el token JWT con rol incluido.
    El mensaje de error es genérico a propósito (no revelar qué campo falla).
    """
    usuario = user_repo.get_user_by_email(data.email)

    # Mismo mensaje para email inexistente o contraseña incorrecta
    if not usuario or not verify_password(data.password, usuario[3]):
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
