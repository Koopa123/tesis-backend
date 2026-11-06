"""
Seguimiento de la señal de una cámara, para medir la disponibilidad.

Cada vez que una cámara deja de enviar video se registra "camara_sin_senal", y
cuando vuelve, "camara_reconectada" con cuánto duró el corte. Con esos eventos
en la auditoría se puede calcular la disponibilidad real de cada cámara en el
horario de atención (gestión de la disponibilidad de ITIL 4).

No depende de la base de datos: quien lo usa decide cómo se avisa (la sesión de
cámara audita directo; el agente edge lo manda al back-end local por HTTP). El
aviso corre en un hilo aparte para no frenar el análisis del video.
"""
import threading
import time
from typing import Callable


def duracion_legible(segundos: float) -> str:
    s = int(round(segundos))
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    if h:
        return f"{h} h {m} min"
    if m:
        return f"{m} min {s} s"
    return f"{s} s"


class SeguimientoSenal:
    def __init__(self, avisar: Callable[[str, str | None], None]):
        self._avisar = avisar
        self.conectada = False
        self.caida_desde: float | None = None

    def _emitir(self, evento: str, detalle: str | None) -> None:
        threading.Thread(target=self._avisar, args=(evento, detalle), daemon=True).start()

    def cuadro_recibido(self) -> None:
        """Llamar con cada cuadro analizado; solo hace algo al recuperarse la señal."""
        if self.conectada:
            return
        self.conectada = True
        if self.caida_desde is not None:
            duracion = time.time() - self.caida_desde
            self.caida_desde = None
            self._emitir("camara_reconectada", f"Sin señal durante {duracion_legible(duracion)}")

    def conexion_perdida(self) -> None:
        """Llamar cuando la lectura de la cámara termina sin que nadie la haya detenido."""
        if self.caida_desde is not None:
            return  # el corte ya está registrado; los reintentos no lo repiten
        self.conectada = False
        self.caida_desde = time.time()
        self._emitir("camara_sin_senal", None)
