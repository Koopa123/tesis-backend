"""
Evita que dos instancias del backend corran a la vez.

Un proceso huérfano (ej. uno matado a la fuerza que no llegó a cerrar bien)
puede quedar vivo compitiendo por la GPU/CPU con una instancia nueva sin que
nadie lo note — la laptop simplemente se siente lenta, sin ningún error que
lo explique. Esto lo convierte en un fallo ruidoso: si ya hay una instancia
corriendo, la nueva se niega a arrancar con un mensaje claro, en vez de
coexistir en silencio.

Funciona reservando un puerto TCP local dedicado (no el de la API) mientras
el proceso vive: el sistema operativo garantiza que solo un proceso puede
tenerlo reservado a la vez.
"""

import socket

LOCK_PORT = 8791

_lock_socket: socket.socket | None = None


def acquire() -> None:
    global _lock_socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", LOCK_PORT))
    except OSError as exc:
        s.close()
        raise RuntimeError(
            "Ya hay otra instancia del backend corriendo (detectado por el "
            f"puerto de bloqueo {LOCK_PORT} ocupado). Cierra ese proceso "
            "antes de arrancar uno nuevo — revisa el Administrador de tareas "
            "por procesos 'python.exe' si no sabes cuál es."
        ) from exc
    _lock_socket = s  # se mantiene reservado mientras el proceso viva


def release() -> None:
    global _lock_socket
    if _lock_socket is not None:
        _lock_socket.close()
        _lock_socket = None
