# Backend — Detección de Aglomeraciones

FastAPI + PostgreSQL (Supabase) + JWT + YOLOv8

## Requisitos

- Python 3.10.4
- Cuenta en [Supabase](https://supabase.com)

---

## 1. Crear las tablas en Supabase

1. Abre tu proyecto en Supabase.
2. Ve a **SQL Editor → New query**.
3. Pega el contenido de `scripts/create_tables.sql` y haz clic en **Run**.

---

## 2. Configurar el entorno

```bash
cp .env.example .env
```

Edita `.env` y rellena:

| Variable | Dónde encontrarla |
|---|---|
| `DATABASE_URL` | Supabase → Settings → Database → Connection string → URI |
| `JWT_SECRET` | Genera uno con `python -c "import secrets; print(secrets.token_hex(32))"` |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | Los que tú elijas para el primer administrador |

---

## 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

---

## 4. Crear el usuario administrador

```bash
python scripts/seed_admin.py
```

El script lee `DATABASE_URL`, `ADMIN_NOMBRE`, `ADMIN_EMAIL` y `ADMIN_PASSWORD` desde `.env`.
Si el email ya existe no crea duplicados.

---

## 5. Iniciar el backend

```bash
python main.py
```

El servidor queda disponible en `http://localhost:8000`.
La documentación interactiva está en `http://localhost:8000/docs`.

---

## 6. Endpoints de autenticación

### `POST /auth/registro`
Crea un usuario con rol **vigilante** (único rol permitido en registro público).

```json
// Request
{ "nombre": "Juan Pérez", "email": "juan@correo.com", "password": "secreto123" }

// Response 201
{
  "token": "eyJ...",
  "usuario": { "id": 1, "nombre": "Juan Pérez", "email": "juan@correo.com", "rol": "vigilante" }
}
```

### `POST /auth/login`
Autentica con email y contraseña.

```json
// Request
{ "email": "juan@correo.com", "password": "secreto123" }

// Response 200
{
  "token": "eyJ...",
  "usuario": { "id": 1, "nombre": "Juan Pérez", "email": "juan@correo.com", "rol": "vigilante" }
}
```

### `GET /auth/me`
Requiere header `Authorization: Bearer <token>`.

```json
// Response 200
{ "id": 1, "nombre": "Juan Pérez", "email": "juan@correo.com", "rol": "vigilante" }
```

---

## 7. Probar en Swagger

1. Abre `http://localhost:8000/docs`.
2. Llama a `POST /auth/registro` o `POST /auth/login`.
3. Copia el `token` de la respuesta.
4. Haz clic en el botón **Authorize** (candado arriba a la derecha).
5. Pega el token y confirma.
6. Ya puedes probar los demás endpoints autenticados.

---

## Roles

| Rol | Cómo se crea | Acceso |
|---|---|---|
| `vigilante` | Registro público (`/auth/registro`) | Endpoints protegidos con `require_auth` |
| `administrador` | Script `seed_admin.py` o insert manual en Supabase | Endpoints protegidos con `require_admin` |

---

## Endpoints RF-1.1 a RF-1.5

### Cámaras IP (RF-1.1)
> La cámara IP solo se registra como configuración. No se verifica conectividad en el prototipo.

| Método | Ruta | Rol requerido |
|---|---|---|
| `POST` | `/api/camaras` | administrador |
| `GET` | `/api/camaras` | autenticado |
| `PATCH` | `/api/camaras/{id}/estado` | administrador |
| `DELETE` | `/api/camaras/{id}` | administrador |

### Fuentes de video (RF-1.2)

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/api/fuentes-video` | Lista fuentes disponibles + cámaras activas |
| `POST` | `/api/fuentes-video/seleccionar` | Valida selección de fuente |

### Grabaciones previas (RF-1.5)

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/api/grabaciones` | Sube video (.mp4/.avi/.mov/.mkv) |
| `GET` | `/api/grabaciones` | Lista grabaciones (admin: todas; vigilante: propias) |

Los archivos se guardan en `uploads/grabaciones/` (carpeta local, no subir al repo).

### Monitoreo (RF-1.3 / RF-1.4)

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/api/monitoreo/iniciar` | Inicia sesión de monitoreo |
| `POST` | `/api/monitoreo/{id}/detener` | Detiene sesión activa |

**Nota sobre el prototipo:**
- `webcam`: el backend crea la sesión; el stream de video viene del navegador (frontend).
- `grabacion_previa`: el backend registra la sesión; el procesamiento de video se integrará en la siguiente fase.
- `camara_ip`: el backend registra la sesión; la conexión real a la cámara queda preparada para integración futura.
