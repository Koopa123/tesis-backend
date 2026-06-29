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
├── main.py                       # Entry point: lanza uvicorn
├── requirements.txt
├── .env.example                  # Plantilla de variables (se comitea)
├── .env                          # Variables reales (NUNCA comitear)
│
├── app/
│   ├── main.py                   # App FastAPI: CORS, lifespan, routers
│   ├── config.py                 # Settings leídas del .env con pydantic-settings
│   ├── database.py               # Pool de conexiones psycopg2 (ThreadedConnectionPool)
│   │
│   ├── core/
│   │   └── security.py           # hash_password, verify_password, create_token,
│   │                             # decode_token, require_auth, require_role, require_admin
│   ├── models/
│   │   └── schemas.py            # Todos los schemas pydantic del proyecto
│   ├── repositories/
│   │   ├── user_repo.py          # create_user, get_user_by_email, get_user_by_id
│   │   ├── camara_repo.py        # CRUD camaras_ip
│   │   ├── grabacion_repo.py     # create_grabacion, list_grabaciones, get_grabacion
│   │   ├── monitoreo_repo.py     # create_sesion, get_sesion, update_estado_sesion
│   │   ├── zona_exclusion_repo.py# CRUD configuraciones_zonas_exclusion
│   │   └── analisis_repo.py      # save_resultado, get_resultado_by_sesion, list_resultados
│   └── routers/
│       ├── auth.py               # POST /auth/registro, POST /auth/login, GET /auth/me
│       ├── camaras.py            # CRUD /api/camaras
│       ├── fuentes_video.py      # GET /api/fuentes-video, POST /api/fuentes-video/seleccionar
│       ├── grabaciones.py        # POST/GET /api/grabaciones, GET /api/grabaciones/{id}/file
│       ├── monitoreo.py          # POST /api/monitoreo/iniciar, POST /api/monitoreo/{id}/detener
│       ├── zonas_exclusion.py    # CRUD /api/zonas-exclusion
│       └── analisis.py           # EP-003: frame webcam, SSE video, historial
│
├── detector/
│   └── yolo_detector.py          # YOLOv8 + BFS + SesionAnalisisState + procesar_video_sync
│
├── uploads/
│   ├── grabaciones/              # Videos subidos (ignorado por git)
│   └── frames/                   # Frames de referencia de zonas (ignorado por git)
│
└── scripts/
    ├── create_tables.sql         # Esquema SQL completo + migraciones
    └── seed_admin.py             # Crea el primer usuario administrador
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
| `FRONTEND_URL` | URL del frontend para referencia |
| `ADMIN_NOMBRE` | Nombre del admin para `seed_admin.py` |
| `ADMIN_EMAIL` | Email del admin para `seed_admin.py` |
| `ADMIN_PASSWORD` | Contraseña del admin para `seed_admin.py` |

> **Importante:** `.env` nunca debe comitearse. `.env.example` sí se comitea.

---

## Base de datos

Tablas activas en Supabase:

| Tabla | Descripción |
|---|---|
| `usuarios` | id, nombre, email (único), password_hash, rol, activo, fecha_creacion |
| `camaras_ip` | id, nombre, direccion_ip, ubicacion, descripcion, activa, fecha_registro |
| `grabaciones` | id, nombre_archivo, ruta_archivo, tipo_contenido, tamanio_bytes, usuario_id, fecha_carga, **fecha_grabacion** |
| `sesiones_monitoreo` | id, usuario_id, tipo_fuente, camara_id, grabacion_id, **zona_exclusion_id**, estado, fecha_inicio, fecha_fin |
| `configuraciones_zonas_exclusion` | id, nombre, frame_referencia, zonas (JSONB), **umbral_medio**, **umbral_alto**, **ventana_segundos**, **cooldown_segundos**, creado_por, activa, fecha_creacion, fecha_actualizacion |
| `resultados_analisis` | id, sesion_id, zona_config_id, personas_maximas, nivel_maximo, tiempo_primera_media_seg, alerta_activada, frames_procesados, inicio_analisis, fin_analisis, fecha_registro |

> Columnas en **negrita** fueron añadidas por migración (ALTER TABLE). Ver `scripts/create_tables.sql`.

---

## Autenticación y roles

### Endpoints `/auth`

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/auth/registro` | Crea usuario con rol `vigilante` |
| `POST` | `/auth/login` | Autentica y devuelve JWT |
| `GET` | `/auth/me` | Devuelve datos del usuario autenticado |

### Formato de respuesta de login/registro

```json
{
  "token": "eyJ...",
  "usuario": { "id": 1, "nombre": "Juan", "email": "j@x.com", "rol": "vigilante" }
}
```

### Roles

| Rol | Cómo se crea | Dependency |
|---|---|---|
| `vigilante` | Registro público | `require_auth` |
| `administrador` | `scripts/seed_admin.py` | `require_admin` |

---

## Endpoints RF-1.1 a RF-1.5

### Cámaras IP — `/api/camaras`
| Método | Ruta | Rol |
|---|---|---|
| POST | `/api/camaras` | administrador |
| GET | `/api/camaras` | autenticado |
| PATCH | `/api/camaras/{id}/estado` | administrador |
| DELETE | `/api/camaras/{id}` | administrador |

### Fuentes de video — `/api/fuentes-video`
| Método | Ruta | Rol |
|---|---|---|
| GET | `/api/fuentes-video` | autenticado |
| POST | `/api/fuentes-video/seleccionar` | autenticado |

### Grabaciones — `/api/grabaciones`
| Método | Ruta | Rol |
|---|---|---|
| POST | `/api/grabaciones` | autenticado |
| GET | `/api/grabaciones` | autenticado |
| GET | `/api/grabaciones/{id}/file` | autenticado (token query param) |

- `fecha_grabacion` (opcional): cuándo fue filmado el video (no cuándo se subió).
- `GET /{id}/file` acepta el JWT como `?token=xxx` porque `<video>` no soporta headers.
- Admin ve todas; vigilante ve solo las propias.

### Monitoreo — `/api/monitoreo`
| Método | Ruta | Rol |
|---|---|---|
| POST | `/api/monitoreo/iniciar` | autenticado |
| POST | `/api/monitoreo/{id}/detener` | autenticado |

- `iniciar` acepta `zona_exclusion_id` opcional para asociar una zona a la sesión.
- `detener` llama a `eliminar_estado(sesion_id)` y guarda resultado en `resultados_analisis` si hubo frames procesados (webcam).

---

## Endpoints RF-2.1 a RF-2.5

### Zonas de exclusión — `/api/zonas-exclusion`
| Método | Ruta | Rol |
|---|---|---|
| POST | `/api/zonas-exclusion` | administrador |
| GET | `/api/zonas-exclusion` | administrador |
| GET | `/api/zonas-exclusion/{id}` | administrador |
| PUT | `/api/zonas-exclusion/{id}` | administrador |
| DELETE | `/api/zonas-exclusion/{id}` | administrador |

**Modelo de datos:**
- `zonas` — JSONB: lista de `{x, y, width, height}` normalizados 0–1 (esquina superior-izquierda + dimensiones)
- `frame_referencia` — ruta relativa de la imagen de referencia (en `uploads/frames/`)
- `umbral_medio` — personas mínimas para nivel Medio (default 4)
- `umbral_alto` — personas mínimas para nivel Alto (default 6); debe ser > umbral_medio
- `ventana_segundos` — duración de la ventana deslizante de alerta (default 2.0 s)
- `cooldown_segundos` — pausa entre alertas consecutivas (default 10 s)
- DELETE hace borrado lógico (`activa = FALSE`), no borra el archivo físico.

---

## Endpoints EP-003 — Análisis de aglomeraciones

### `/api/analisis`
| Método | Ruta | Rol | Descripción |
|---|---|---|---|
| POST | `/api/analisis/frame` | autenticado | Frame webcam → detecciones + stats acumuladas |
| GET | `/api/analisis/video/{sesion_id}/stream` | autenticado | SSE de análisis de grabación previa |
| GET | `/api/analisis/historial` | autenticado | Historial de resultados guardados |
| GET | `/api/analisis/resultado/{sesion_id}` | autenticado | Resultado de una sesión específica |

### `POST /api/analisis/frame`

Form fields: `sesion_id` (int), `frame` (JPEG blob), `zona_config_id` (int, opcional).

Respuesta:
```json
{
  "sesion_id": 5,
  "personas": 3,
  "total_personas": 4,
  "nivel": "medio",
  "alerta": false,
  "detecciones": [{"x1":0.1,"y1":0.2,"x2":0.3,"y2":0.8,"conf":0.87,"excluida":false}],
  "personas_maximas": 5,
  "nivel_maximo": "alto",
  "tiempo_primera_media_seg": 2.4,
  "alerta_activada": true
}
```

- `personas` = tamaño del **grupo más grande** (BFS sobre bottom-centers).
- `total_personas` = total no excluidas (sin agrupar).
- El estado de sesión se crea en el primer frame y se cachea en memoria.

### `GET /api/analisis/video/{sesion_id}/stream`

Server-Sent Events (SSE). El cliente usa `fetch + ReadableStream` (no `EventSource` nativo, que no soporta `Authorization` header).

Eventos:
```
data: {"tipo":"frame","frame_num":8,"total_frames":240,"progreso":3.3,"timestamp_video":0.27,"personas":2,"nivel":"bajo","alerta":false,"detecciones":[...]}
data: {"tipo":"fin","personas_maximas":6,"nivel_maximo":"alto","tiempo_primera_media_seg":4.1,"alerta_activada":true,"frames_procesados":60}
data: {"tipo":"error","mensaje":"No se pudo abrir el archivo de video."}
```

- Procesa a ~8 fps máximo (salta frames intermedios).
- El resultado se guarda automáticamente en `resultados_analisis` al terminar el stream.

---

## Módulo detector — `detector/yolo_detector.py`

### Funciones principales

| Función | Descripción |
|---|---|
| `procesar_frame(frame_bytes, zonas_exclusion, umbral_medio, umbral_alto)` | Detecta personas en un JPEG, aplica zonas, BFS, clasifica nivel |
| `procesar_video_sync(ruta, zona_config, estado, callback, cancelado_fn)` | Procesa video completo frame a frame, llama callback por cada evento |
| `crear_estado(sesion_id, zona_config)` | Crea y registra un `SesionAnalisisState` en memoria |
| `obtener_estado(sesion_id)` | Retorna estado en memoria o None |
| `eliminar_estado(sesion_id)` | Elimina estado y retorna su valor |

### Lógica de exclusión de zonas (RF-3.2)

`_en_zona_exclusion(x1, y1, x2, y2, zonas)` — excluye si:
1. El **centro del bbox** cae dentro de la zona, O
2. Al menos el **25 % del área del bbox** intersecta la zona.

Usar el bbox completo (no solo el punto inferior) evita falsos positivos con maniquíes y objetos altos.

### Agrupación BFS (RF-3.3)

`_agrupar_bfs(puntos, umbral_dist=0.20)` agrupa personas cuyo bottom-center está a ≤ 0.20 (normalizado) entre sí. `personas` en la respuesta = tamaño del grupo más grande.

### Ventana deslizante de alerta (RF-3.4)

`SesionAnalisisState.actualizar(personas, nivel)`:
- Mantiene una `deque` de `(timestamp, nivel)` para la ventana temporal.
- Dispara alerta si ≥ 70 % de los frames en la ventana son "alto" Y hay al menos 3 frames.
- Respeta el `cooldown_segundos` entre alertas.

### RF-3.5 — Tiempo hasta primera detección media

`tiempo_primera_media` registra los segundos desde el inicio de la sesión hasta el primer frame con nivel ≥ "medio".

---

## Reglas para futuras modificaciones

- No cambiar la estructura de respuesta de `/auth/*` sin coordinar con el frontend React/Vite.
- Mantener nombres en español en las respuestas JSON: `usuario`, `nombre`, `rol`, `token`.
- No exponer secretos, contraseñas ni tokens en logs ni respuestas de error.
- No subir al repositorio: modelos `.pt`/`.pth`/`.onnx`, videos, archivos `.env`.
- Los endpoints protegidos usan `Depends(require_auth)` o `Depends(require_admin)`.
- Para proteger un endpoint por rol: `Depends(require_role("administrador"))`.
- No conectar cámaras IP reales sin implementar el módulo de streaming.
- No abrir webcam desde el backend; el video viene del frontend.
- `uploads/grabaciones/` y `uploads/frames/` nunca se comitean.
- Todos los repos usan índices de tupla sobre `_COLS` explícito — verificar índices al agregar columnas.
- El modelo YOLO se carga de forma perezosa con un singleton protegido por `threading.Lock`.

---

## Frontend (React + TypeScript + Vite + Tailwind v4)

### Estructura relevante

```
frontend/src/
├── types/
│   ├── api.ts          # CameraIP, Recording, MonitoringSession, DetectionBox,
│   │                   # FrameAnalysisResult, AnalysisResult, VideoSSEEvent, …
│   └── zones.ts        # ExclusionRect, ExclusionZoneConfig (con umbrales)
├── services/
│   ├── apiClient.ts        # apiFetch con Bearer token
│   ├── authService.ts      # login, register, getMe
│   ├── cameraService.ts    # CRUD cámaras IP
│   ├── videoSourceService.ts
│   ├── recordingService.ts # uploadRecording(file, fechaGrabacion?)
│   ├── monitoringService.ts# startMonitoring, stopMonitoring
│   ├── exclusionZoneService.ts # CRUD zonas con umbrales
│   └── analisisService.ts  # analyzeFrame, streamVideoAnalisis, getHistorial
└── pages/dashboard/
    ├── DashboardHome.tsx
    ├── MonitoreoPage.tsx   # Webcam (canvas overlay + BFS stats) + Video SSE player
    ├── GrabacionesPage.tsx # Subir videos con fecha_grabacion opcional
    ├── CamarasPage.tsx
    ├── ZonasExclusionPage.tsx # Editor de zonas + umbrales de detección
    └── HistorialPage.tsx   # Lista de resultados_analisis
```

### Flujo webcam (MonitoreoPage)

1. `getUserMedia` → `<video>` element.
2. `setInterval` cada 500 ms → captura frame a canvas oculto → `canvas.toBlob`.
3. `analyzeFrame(sesionId, blob, zonaConfigId)` → `POST /api/analisis/frame`.
4. Respuesta dibujada en canvas overlay: zonas (violeta punteado) + bboxes (cyan/gris).
5. **Stale closure evitada con refs**: `sessionRef`, `selectedZoneIdRef`, `currentZoneRectsRef`, `captureCallbackRef` se actualizan en cada render.

### Flujo grabación previa (MonitoreoPage)

1. `streamVideoAnalisis(sesionId, onEvent)` → `fetch + ReadableStream` (SSE manual).
2. `<video src="/api/grabaciones/{id}/file?token=...">` se reproduce en paralelo.
3. `requestAnimationFrame` loop dibuja `latestVideoDetRef.current` sobre canvas overlay.
4. Evento `fin` → resumen final, detener RAF.

### Zonas de exclusión (ZonasExclusionPage)

- El administrador sube una imagen de referencia (o extrae un frame de video con slider + canvas).
- Dibuja rectángulos sobre la imagen con `ZoneEditor`.
- Configura umbrales: `umbral_medio`, `umbral_alto`, `ventana_segundos`, `cooldown_segundos`.
- Coordenadas guardadas normalizadas 0–1 (independientes de resolución).

---

## Estado de implementación

| Requisito | Estado |
|---|---|
| RF-1.1 Cámaras IP | ✅ Implementado |
| RF-1.2 Fuentes de video | ✅ Implementado |
| RF-1.3 Grabaciones | ✅ Implementado |
| RF-1.4 Monitoreo webcam | ✅ Implementado |
| RF-1.5 Monitoreo grabación previa | ✅ Implementado |
| RF-2.1–2.5 Zonas de exclusión | ✅ Implementado |
| RF-3.1 Detección YOLO | ✅ Implementado (yolov8n.pt) |
| RF-3.2 Exclusión de zonas | ✅ Implementado (bbox + área) |
| RF-3.3 Clasificación de niveles | ✅ Implementado (BFS grupos) |
| RF-3.4 Alerta sostenida | ✅ Implementado (ventana deslizante 70 %) |
| RF-3.5 Tiempo primera detección media | ✅ Implementado |
| Historial de análisis | ✅ Implementado |
