from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Base de datos
    database_url: str

    # JWT
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 24

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
