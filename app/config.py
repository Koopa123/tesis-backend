from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Base de datos
    database_url: str

    # JWT
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 24

    # Edge (laptop en el local): clave compartida para /api/edge/*
    edge_api_key: str = ""

    # Clave Fernet para cifrar las contraseñas RTSP en la BD. Debe ser la
    # MISMA en la laptop del local y en Railway, porque las dos usan la misma
    # base. Generar con: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    rtsp_enc_key: str = ""

    # Vigencia de los tickets que reemplazan al JWT en la URL de <img>/<video>
    media_ticket_segundos: int = 60
    media_ticket_grabacion_segundos: int = 1800

    # Días que se conservan las evidencias (D.S. 007-2020-IN: mínimo 45;
    # Directiva 01-2020-JUS/DGTAIPD: máximo 60). 0 desactiva el borrado.
    retencion_dias: int = 60

    # Carpetas de archivos
    grabaciones_folder: str = "uploads/grabaciones"
    zonas_frames_folder: str = "uploads/frames"

    # CORS — en prod cambia esto a tu dominio real
    allowed_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """
    Singleton cacheado: la configuración se lee del .env una sola vez
    y se reutiliza en toda la app (inyectable con Depends).
    """
    return Settings()
