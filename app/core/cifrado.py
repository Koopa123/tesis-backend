"""
Cifrado en reposo de las contraseñas RTSP de las cámaras (Fernet: AES-128-CBC + HMAC).

Los valores cifrados se guardan con el prefijo "fernet:". Un valor sin prefijo es
una contraseña antigua en texto plano: se sigue aceptando para no cortar las
cámaras ya registradas, y scripts/cifrar_rtsp_passwords.py las convierte.
"""
import logging

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

logger = logging.getLogger(__name__)

PREFIJO = "fernet:"


def _fernet() -> Fernet | None:
    clave = get_settings().rtsp_enc_key
    if not clave:
        return None
    return Fernet(clave.encode())


def cifrar(valor: str | None) -> str | None:
    """Cifra una contraseña RTSP. Vacío o None se guardan tal cual."""
    if not valor or valor.startswith(PREFIJO):
        return valor
    f = _fernet()
    if f is None:
        logger.warning("RTSP_ENC_KEY no está configurada: la contraseña RTSP se guarda sin cifrar")
        return valor
    return PREFIJO + f.encrypt(valor.encode()).decode()


def descifrar(valor: str | None) -> str | None:
    """Devuelve la contraseña en claro, solo para armar la URL RTSP."""
    if not valor or not valor.startswith(PREFIJO):
        return valor
    f = _fernet()
    if f is None:
        logger.error("Hay contraseñas RTSP cifradas pero RTSP_ENC_KEY no está configurada")
        return ""
    try:
        return f.decrypt(valor[len(PREFIJO):].encode()).decode()
    except InvalidToken:
        logger.error("No se pudo descifrar una contraseña RTSP: RTSP_ENC_KEY no coincide con la usada al cifrarla")
        return ""
