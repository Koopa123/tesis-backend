FROM python:3.10-slim

WORKDIR /app

# Librerías de sistema:
# - libgl1-mesa-glx, libglib2.0-0, libsm6, libxext6, libxrender-dev: las que
#   pide opencv-python normal (no headless) — esta es la combinación que ya
#   funcionaba antes en el backend anterior, se vuelve a esa base.
# - libpq5: cliente de PostgreSQL (psycopg2-binary lo necesita en el sistema)
# - libgomp1: runtime OpenMP (numpy/opencv lo usan por debajo)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libpq5 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Invalida el cache de Docker desde aquí en adelante (cambiar este valor fuerza
# un rebuild real; Railway estaba reusando capas viejas en caché sin avisar).
ARG CACHEBUST=20261111a

# Sin PyTorch ni ultralytics ni pesos de YOLO: en la nube no se analiza video (las cámaras están en la red
# privada del local y la detección corre en la laptop). El backend arranca igual porque el detector se puede
# importar sin ellos (DETECCION_DISPONIBLE = False) y iniciar un análisis aquí responde 503 con un mensaje.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Forma shell (no exec/JSON) a propósito: Railway inyecta el puerto real en la
# variable $PORT en tiempo de ejecución, y solo la forma shell expande
# variables de entorno en el CMD. El fallback a 8000 es para correr el
# contenedor en local sin definir PORT.
# --proxy-headers: detrás del proxy de Railway, request.client.host debe ser
# la IP real del cliente (la usa el límite de intentos de login en auth.py).
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips="*"
