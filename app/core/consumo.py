"""
Registro periódico del consumo de energía de la laptop del local.

Mientras el backend local está encendido, CodeCarbon mide la energía del equipo
(la GPU con NVML; la CPU y la RAM, estimadas) y cada hora agrega una fila a
`registro_consumo/consumo.csv`. Con ese archivo se arma el seguimiento diario
y mensual (`scripts/resumen_consumo.py`) que pide el anexo de software verde.

Solo corre en la laptop: en Railway no se analiza video y CodeCarbon no está
instalado, así que se omite sin error. Se desactiva con CONSUMO_REGISTRO=0.
"""
import logging
import os
import threading

logger = logging.getLogger(__name__)

CARPETA = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                       "registro_consumo")
ARCHIVO = "consumo.csv"
PERIODO_SEGUNDOS = 3600          # una fila por hora encendida
MEDIR_CADA_SEGUNDOS = 60         # muestreo de CodeCarbon: bajo, para no sumar carga
_detener = threading.Event()
_hilo: threading.Thread | None = None


def _nuevo_tracker():
    from codecarbon import OfflineEmissionsTracker
    kwargs = dict(project_name="crowdsense", country_iso_code="PER", output_dir=CARPETA,
                  output_file=ARCHIVO, measure_power_secs=MEDIR_CADA_SEGUNDOS, log_level="error",
                  save_to_file=True)
    try:
        # Si hay otra medición en curso (un script de pruebas), no debe impedir esta.
        return OfflineEmissionsTracker(allow_multiple_runs=True, **kwargs)
    except TypeError:
        return OfflineEmissionsTracker(**kwargs)


def _bucle():
    while not _detener.is_set():
        try:
            tracker = _nuevo_tracker()
            tracker.start()
        except Exception:
            logger.exception("No se pudo iniciar el registro de consumo; se reintenta en una hora")
            _detener.wait(PERIODO_SEGUNDOS)
            continue
        _detener.wait(PERIODO_SEGUNDOS)
        try:
            tracker.stop()          # escribe la fila del periodo en el CSV
        except Exception:
            logger.exception("No se pudo guardar la fila de consumo")


def iniciar():
    global _hilo
    if os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("CONSUMO_REGISTRO", "1") == "0":
        return
    try:
        import codecarbon  # noqa: F401
    except ImportError:
        logger.info("CodeCarbon no está instalado: no se registra el consumo de energía")
        return
    os.makedirs(CARPETA, exist_ok=True)
    _detener.clear()
    _hilo = threading.Thread(target=_bucle, daemon=True, name="registro-consumo")
    _hilo.start()
    logger.info("Registro de consumo activo: %s", os.path.join(CARPETA, ARCHIVO))


def detener():
    _detener.set()
    if _hilo is not None:
        _hilo.join(timeout=20)    # deja que stop() escriba la última fila
