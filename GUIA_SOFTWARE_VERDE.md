# Guía de codificación verde — backend y agente de borde

Reglas para que CrowdSense AI haga su trabajo con la menor energía posible. Casi todo el consumo está en el
análisis de video con YOLOv8m en la laptop del local, así que la mayoría de las reglas apuntan ahí.
Todo cambio nuevo debe respetarlas; si alguno no puede cumplir una, hay que explicar el motivo en el commit.

## Análisis de video

1. **Una cámara se analiza una sola vez.** Antes de abrir un RTSP, reutilizar la sesión viva de esa cámara
   (`iniciar_monitoreo` en `app/routers/monitoreo.py`). El agente (`edge_agent.py`) consulta `GET /api/edge/local` y cede la
   cámara si el back-end local ya la analiza.
2. **Leer siempre el último cuadro.** La lectura RTSP va en su propio hilo y solo guarda el cuadro más reciente
   (`procesar_rtsp_mjpeg` en `detector/yolo_detector.py`); no se procesan cuadros atrasados.
3. **Un solo modelo cargado, en media precisión.** Todas las cámaras comparten el mismo modelo, en la GPU cuando
   existe, protegido por `_inference_lock`, y en FP16 (`MEDIA_PRECISION`, todas las llamadas con `half=`). No
   cargar un modelo por cámara ni por petición.
4. **No codificar ni decodificar dos veces.** El búfer del clip reutiliza los mismos JPEG que ya se generan para el
   video en vivo, y el detector recibe el cuadro ya decodificado (`procesar_frame(..., frame=frame)`) en vez de
   volver a descomprimir el JPEG.
5. **Bajar el ritmo con batería.** Sin cargador se analizan a lo sumo 5 cuadros por segundo por cámara
   (`FPS_EN_BATERIA`); al volver la corriente se retoma el ritmo normal.
6. **Detener lo que nadie usa.** Una sesión de cámara termina 120 s después de que se va el último espectador
   (`_GRACIA_SIN_ESPECTADORES` en `app/routers/analisis.py`).

## Datos y red

7. **No subir video a la nube.** A Railway solo viajan los resultados (menos de 1 KB cada 5 s) y una foto cuando hay
   alerta.
8. **Guardar evidencia solo cuando hace falta.** El clip se graba solo si hay alerta, y las fotos y los clips se
   borran a los 60 días (`app/core/retencion.py`).
9. **No consultar la base de datos por cada cuadro.** Las vistas se registran en la auditoría una vez cada 10 min
   por usuario y recurso, y los listados llevan límite de filas.
10. **Trabajo pesado, en hilo aparte y solo cuando corresponde.** Escribir el clip y el respaldo de la base de datos
   no debe frenar el análisis en vivo.

## Medición

11. **Registrar el consumo.** El backend local deja una fila por hora en `registro_consumo/consumo.csv`
    (`app/core/consumo.py`); `scripts/resumen_consumo.py` lo resume por día y por mes.
12. **Medir antes de aceptar un cambio que afecte al análisis.** Comparar la potencia de la GPU (nvidia-smi) y la
    del equipo (CodeCarbon) con la última medición del anexo de software verde. Si el consumo sube, el commit debe
    explicar por qué el cambio lo vale.
