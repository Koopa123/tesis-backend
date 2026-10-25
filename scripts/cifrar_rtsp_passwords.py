"""
Cifra las contraseñas RTSP que todavía están en texto plano en camaras_ip.

Uso (desde tesis-backend, con DATABASE_URL y RTSP_ENC_KEY en el .env):
    python scripts/cifrar_rtsp_passwords.py

Es idempotente: las contraseñas que ya empiezan con "fernet:" no se tocan.
Antes de correrlo, la MISMA RTSP_ENC_KEY debe estar en la laptop del local y en
Railway; si no, la instancia sin la clave no podrá abrir las cámaras.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import get_settings  # noqa: E402
from app.core.cifrado import PREFIJO, cifrar, descifrar  # noqa: E402
from app.database import close_pool, init_pool  # noqa: E402
from app.repositories import camara_repo  # noqa: E402


def main() -> None:
    if not get_settings().rtsp_enc_key:
        sys.exit("Falta RTSP_ENC_KEY en el .env: no se cifra nada.")
    init_pool()
    try:
        cifradas = 0
        for camara in camara_repo.list_camaras():
            camara_id, nombre, password = camara[0], camara[1], camara[8]
            if not password or password.startswith(PREFIJO):
                continue
            valor = cifrar(password)
            assert descifrar(valor) == password
            camara_repo.set_password_cifrada(camara_id, valor)
            cifradas += 1
            print(f"Cámara {camara_id} ({nombre}): contraseña cifrada")
        print(f"Listo: {cifradas} contraseña(s) cifrada(s).")
    finally:
        close_pool()


if __name__ == "__main__":
    main()
