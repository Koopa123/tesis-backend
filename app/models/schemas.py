from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field


# ── Auth ─────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=100, examples=["Ana García"])
    email: EmailStr = Field(..., examples=["ana@ejemplo.com"])
    password: str = Field(..., min_length=6, examples=["s3cr3to"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    nombre: str
    email: str
    rol: str


class AuthResponse(BaseModel):
    token: str
    usuario: UserOut


# ── Presets ──────────────────────────────────────────────────────────────────

class ZonasRequest(BaseModel):
    """
    Lista de zonas ignoradas. Cada zona es [x1, y1, x2, y2] en píxeles.
    Ejemplo: [[0, 0, 100, 80], [500, 300, 640, 480]]
    """
    zonas: list[list[int]]


class PresetOut(BaseModel):
    id: int
    nombre: str
    frame_url: str
    zonas: list[Any]
    fecha_creacion: str | None


class PresetsListOut(BaseModel):
    presets: list[PresetOut]


# ── Análisis ─────────────────────────────────────────────────────────────────

class AnalisisOut(BaseModel):
    id: int
    nombre_video: str
    personas_maximas: int
    grupo_mayor_maximo: int
    nivel_final: str
    fecha: str | None
    preset_nombre: str | None


class AnalisisListOut(BaseModel):
    analisis: list[AnalisisOut]


class AnalisisUploadResponse(BaseModel):
    mensaje: str
    nombre_video: str
    stream_url: str
