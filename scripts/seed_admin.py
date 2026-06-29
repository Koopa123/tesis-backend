"""
Crea un usuario administrador en la base de datos.

Uso:
    # Opción 1: con variables de entorno definidas en .env
    python scripts/seed_admin.py

    # Opción 2: pasando valores en línea
    ADMIN_NOMBRE="Admin" ADMIN_EMAIL="admin@correo.com" ADMIN_PASSWORD="secreto" \
        python scripts/seed_admin.py

Variables requeridas (en .env o entorno):
    DATABASE_URL    Cadena de conexión PostgreSQL
    ADMIN_EMAIL     Email del administrador
    ADMIN_PASSWORD  Contraseña del administrador

Variables opcionales:
    ADMIN_NOMBRE    Nombre visible (default: "Administrador")
"""

import os
import sys

# Cargar .env si existe
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv no instalado; se leen las vars del entorno directamente

import psycopg2
from passlib.context import CryptContext

DATABASE_URL   = os.environ.get("DATABASE_URL")
ADMIN_NOMBRE   = os.environ.get("ADMIN_NOMBRE", "Administrador")
ADMIN_EMAIL    = os.environ.get("ADMIN_EMAIL")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")

# ── Validación de variables ───────────────────────────────────────────────────
missing = [v for v, val in [
    ("DATABASE_URL",   DATABASE_URL),
    ("ADMIN_EMAIL",    ADMIN_EMAIL),
    ("ADMIN_PASSWORD", ADMIN_PASSWORD),
] if not val]

if missing:
    print(f"Error: faltan las siguientes variables de entorno: {', '.join(missing)}")
    print("Defínelas en .env o pásalas antes del comando.")
    sys.exit(1)

# ── Hash de contraseña ────────────────────────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
password_hash = pwd_context.hash(ADMIN_PASSWORD)

# ── Conexión y seed ───────────────────────────────────────────────────────────
try:
    conn = psycopg2.connect(DATABASE_URL)
except psycopg2.OperationalError as e:
    print(f"No se pudo conectar a la base de datos: {e}")
    sys.exit(1)

try:
    with conn.cursor() as cur:
        # Verificar si el email ya existe
        cur.execute("SELECT id, rol FROM usuarios WHERE email = %s", (ADMIN_EMAIL,))
        existing = cur.fetchone()

        if existing:
            existing_id, existing_rol = existing
            print(f"Ya existe un usuario con email '{ADMIN_EMAIL}' (id={existing_id}, rol={existing_rol}).")
            print("No se creó ningún duplicado.")
            sys.exit(0)

        cur.execute(
            """
            INSERT INTO usuarios (nombre, email, password_hash, rol)
            VALUES (%s, %s, %s, 'administrador')
            RETURNING id
            """,
            (ADMIN_NOMBRE, ADMIN_EMAIL, password_hash),
        )
        admin_id = cur.fetchone()[0]

    conn.commit()
    print("Administrador creado correctamente.")
    print(f"  id:     {admin_id}")
    print(f"  nombre: {ADMIN_NOMBRE}")
    print(f"  email:  {ADMIN_EMAIL}")
    print(f"  rol:    administrador")

finally:
    conn.close()
