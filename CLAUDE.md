# CrowdSense AI — Backend

Sistema de detección y clasificación de aglomeraciones en videos usando YOLOv8.
Expone una API REST con autenticación JWT y roles de usuario.

---

## Stack

| Componente | Versión |
|---|---|
| Python | 3.10.4 |
| FastAPI | 0.115.0 |
| Uvicorn | 0.30.6 |
| Base de datos | Supabase PostgreSQL |
| Driver BD | psycopg2-binary 2.9.9 |
| Auth | JWT Bearer (python-jose 3.3.0) |
| Hashing | passlib 1.7.4 + bcrypt 4.0.1 |
| Validación | pydantic v2 + pydantic-settings |
| Detección | YOLOv8 (ultralytics 8.2.91) + OpenCV |

---

## Comandos

```bash
# Activar entorno virtual (Windows)
.venv\Scripts\activate

# Instalar dependencias
python -m pip install -r requirements.txt

# Ejecutar backend
python main.py
# o bien
uvicorn app.main:app --reload
```

La API queda disponible en `http://localhost:8000`.
Documentación interactiva en `http://localhost:8000/docs`.

---

## Estructura del proyecto

```
backend/
├── main.py                  # Entry point: lanza uvicorn
├── requirements.txt
├── .env.example             # Plantilla de variables (se comitea)
├── .env                     # Variables reales (NUNCA comitear)
│
├── app/
│   ├── main.py              # App FastAPI: CORS, lifespan, routers
│   ├── config.py            # Settings leídas del .env con pydantic-settings
│   ├── database.py          # Pool de conexiones psycopg2 (ThreadedConnectionPool)
│   │
│   ├── core/
│   │   └── security.py      # hash_password, verify_password, create_token,
│   │                        # decode_token, require_auth, require_role, require_admin
│   ├── models/
│   │   └── schemas.py       # Schemas pydantic: RegisterRequest, LoginRequest,
│   │                        # UserOut, AuthResponse, PresetOut, AnalisisOut, …
│   ├── repositories/
│   │   ├── user_repo.py     # create_user, get_user_by_email, get_user_by_id
│   │   ├── preset_repo.py   # CRUD de presets
│   │   └── analisis_repo.py # save_analisis, list_analisis
│   └── routers/
│       ├── auth.py          # POST /auth/registro, POST /auth/login, GET /auth/me
│       ├── presets.py       # CRUD /presets
│       └── analisis.py      # POST /analisis, GET /analisis, GET /analisis/stream/{nombre}
│
├── detector/
│   └── detector.py          # Detección YOLOv8 + agrupación BFS + stream MJPEG
│
└── scripts/
    ├── create_tables.sql    # Esquema SQL para ejecutar en Supabase (una sola vez)
    └── seed_admin.py        # Crea el primer usuario administrador
```

---

## Variables de entorno

Copiar `.env.example` como `.env` y rellenar:

| Variable | Descripción |
|---|---|
| `DATABASE_URL` | URI de conexión PostgreSQL de Supabase |
| `JWT_SECRET` | Secreto para firmar tokens JWT (mínimo 32 chars aleatorios) |
| `JWT_ALGORITHM` | Algoritmo JWT (default: `HS256`) |
| `JWT_EXPIRE_HOURS` | Duración del token en horas (default: `24`) |
| `FRONTEND_URL` | URL del frontend para referencia (no usada en CORS directamente) |
| `ADMIN_NOMBRE` | Nombre del admin para `seed_admin.py` |
| `ADMIN_EMAIL` | Email del admin para `seed_admin.py` |
| `ADMIN_PASSWORD` | Contraseña del admin para `seed_admin.py` |

> **Importante:** `.env` nunca debe comitearse. `.env.example` sí se comitea.
>
> Si la contraseña contiene caracteres especiales (`@`, `#`, `%`), encodéalos en la URL:
> `@` → `%40`, `#` → `%23`, `%` → `%25`

---

## Base de datos

Ejecutar `scripts/create_tables.sql` en **Supabase → SQL Editor → New query** (solo una vez).

Tablas:
- `usuarios` — id, nombre, email (único), password_hash, rol, activo, fecha_creacion
- `presets` — id, nombre, frame_path, zonas (JSONB), fecha_creacion
- `analisis` — id, nombre_video, personas_maximas, grupo_mayor_maximo, nivel_final, preset_id, fecha

---

## Autenticación y roles

### Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/auth/registro` | Crea usuario con rol `vigilante` |
| `POST` | `/auth/login` | Autentica y devuelve JWT |
| `GET` | `/auth/me` | Devuelve datos del usuario autenticado |

### Formato de respuesta

```json
{
  "token": "eyJ...",
  "usuario": {
    "id": 1,
    "nombre": "Juan Pérez",
    "email": "juan@correo.com",
    "rol": "vigilante"
  }
}
```

### Roles

| Rol | Cómo se crea | Dependency de protección |
|---|---|---|
| `vigilante` | Registro público (`/auth/registro`) | `require_auth` |
| `administrador` | `scripts/seed_admin.py` o insert manual en Supabase | `require_admin` |

El registro público **siempre** asigna `rol = "vigilante"` en el servidor.
El frontend no puede enviar ni modificar el rol.

### Crear administrador

```bash
# Con variables ya en .env:
python scripts/seed_admin.py
```

---

## Reglas para futuras modificaciones

- No cambiar la estructura de respuesta de `/auth/*` sin coordinar con el frontend React/Vite.
- Mantener nombres en español en las respuestas JSON: `usuario`, `nombre`, `rol`, `token`.
- No exponer secretos, contraseñas ni tokens en logs ni respuestas de error.
- No subir al repositorio: modelos `.pt`/`.pth`/`.onnx`, videos, archivos `.env`.
- No implementar procesamiento YOLO o análisis de video salvo instrucción explícita.
- Los endpoints protegidos usan `Depends(require_auth)` o `Depends(require_admin)`.
- Para proteger un endpoint por rol: `Depends(require_role("administrador"))`.

---

## Estado actual

- Auth completa con Supabase funcionando (registro, login, /me).
- JWT incluye `sub`, `email`, `rol`, `exp`.
- `/auth/me` consulta BD real (no devuelve datos del token solamente).
- Roles `vigilante` y `administrador` operativos.
- Endpoints de presets y análisis con YOLO presentes pero no modificados.
