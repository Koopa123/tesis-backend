"""Estado compartido de sesiones RTSP activas. Importado por analisis.py y monitoreo.py."""
import threading

_sessions: dict[int, dict] = {}
_lock = threading.Lock()


def set_session(sesion_id: int, data: dict) -> None:
    with _lock:
        _sessions[sesion_id] = data


def get_session(sesion_id: int) -> dict | None:
    return _sessions.get(sesion_id)


def cancel_session(sesion_id: int) -> None:
    """Señaliza al hilo RTSP que se detenga y elimina la entrada."""
    with _lock:
        data = _sessions.pop(sesion_id, None)
    if data:
        data["cancelado"].set()


def cancel_all_sessions() -> None:
    """
    Señaliza a TODOS los hilos de sesión (RTSP y video previa) que se detengan.
    Se llama al apagar la app: sin esto, los hilos en background siguen usando
    la GPU y el pool de BD mientras el proceso intenta cerrar, y el cierre se
    queda colgado esperando algo que nunca se le avisó que debía parar.
    """
    with _lock:
        sesiones = list(_sessions.values())
        _sessions.clear()
    for data in sesiones:
        data["cancelado"].set()
