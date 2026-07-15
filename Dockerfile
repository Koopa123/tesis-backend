FROM python:3.10-slim

WORKDIR /app

# Librerías de sistema necesarias en runtime:
# - libpq5: cliente de PostgreSQL (psycopg2-binary la necesita en el sistema)
# - libgomp1: runtime OpenMP (numpy/opencv/torch la usan por debajo)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# torch/torchvision: build CPU explícita, evita bajar CUDA (Railway no tiene GPU)
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch torchvision

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Fuerza que quede la variante headless (ultralytics arrastra opencv-python normal)
RUN pip install --no-cache-dir --force-reinstall --no-deps opencv-python-headless==4.10.0.84

COPY . .

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
