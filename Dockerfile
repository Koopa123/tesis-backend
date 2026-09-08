FROM python:3.10-slim

WORKDIR /app

# Librerías de sistema:
# - libgl1-mesa-glx, libglib2.0-0, libsm6, libxext6, libxrender-dev: las que
#   pide opencv-python normal (no headless) — esta es la combinación que ya
#   funcionaba antes en el backend anterior, se vuelve a esa base.
# - libpq5: cliente de PostgreSQL (psycopg2-binary lo necesita en el sistema)
# - libgomp1: runtime OpenMP (numpy/torch lo usan por debajo)
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
ARG CACHEBUST=20260908a

# torch/torchvision: build CPU explícita, evita bajar CUDA (Railway no tiene GPU).
# Versión fijada (no la más nueva): sospecha de conflicto de threads (OpenMP)
# entre una build de torch muy reciente y esta versión de opencv.
# --extra-index-url (no --index-url): con --index-url pip resuelve TODAS las
# dependencias transitivas (typing-extensions, sympy, filelock...) solo desde
# el índice de PyTorch, que no las tiene todas. Un release nuevo de
# typing_extensions rompió esa resolución (mismatch de nombre de wheel) y pip
# cayó a compilar desde sdist, que pide flit_core y falla porque ese índice
# restringido no lo tiene. Con --extra-index-url, PyPI queda disponible como
# respaldo para esas dependencias.
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu torch==2.1.2 torchvision==0.16.2

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Diagnóstico: prueba cv2.resize DESPUÉS de importar torch (orden real de la app),
# para confirmar si el conflicto es específicamente por tener ambos cargados juntos.
RUN python -c "import torch; import cv2, numpy as np; img = np.zeros((480,640,3), dtype=np.uint8); out = cv2.resize(img, (416,416)); print('cv2.resize con torch importado OK:', out.shape)"

# Descarga los pesos de YOLOv8 AHORA (en el build, con red garantizada) para que
# queden dentro de la imagen. El .pt está en .gitignore a propósito (no se sube a git),
# así que sin este paso el contenedor lo intentaría descargar en cada arranque.
RUN python -c "from ultralytics import YOLO; YOLO('yolov8s.pt')"

COPY . .

EXPOSE 8000

# Forma shell (no exec/JSON) a propósito: Railway inyecta el puerto real en la
# variable $PORT en tiempo de ejecución, y solo la forma shell expande
# variables de entorno en el CMD. El fallback a 8000 es para correr el
# contenedor en local sin definir PORT.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
