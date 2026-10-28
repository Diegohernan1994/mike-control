# Estado — 2026-10-28, entrega de backend base

## Implementado en código, pendiente de instalar
- Prototipo original conservado en web/index.html.
- Panel servido por FastAPI en web/app.html y web/app.js.
- Acceso de propietario por HTTP Basic; sin credenciales por defecto y requiere HTTPS en proxy.
- Historial de mensajes por agente en PostgreSQL, máximo 100 mensajes recientes por consulta.
- Creación idempotente de tabla e índice, transacciones y consultas parametrizadas.
- Rutas de salud de proceso y de base, errores de DB sin devolver detalles sensibles.
- Dockerfile con usuario sin privilegios y dependencias de ejecución fijadas.
- Guía de instalación y variables en docs/easypanel.md.

## Pruebas
Verificado en GitHub Actions con PostgreSQL 18: pruebas API y persistencia real, dependencias, JavaScript, construcción Docker y prueba del contenedor con autenticación y conservación de mensajes tras reinicio. Todas las etapas pasaron.
Evidencia: https://github.com/Diegohernan1994/mike-control/actions/runs/40696773955
Código verificado: ee482fa719453e774aac24f54df468d0cd2137ad.
No se ha conectado la base de DonWeb ni desplegado en Easypanel. La validación de infraestructura del propietario queda para instalación.

## Infraestructura informada por el propietario
Easypanel en DonWeb, separado de las Droplets supervisadas. Servicios mike-db y mike-app creados. Captura de PostgreSQL muestra listo para aceptar conexiones. Aplicación aún sin implementar; no se han recibido credenciales.

## No implementado
OpenAI y respuestas de agentes, memoria semántica/resúmenes, SSH, métricas, scheduler cada 15 minutos, incidentes, Telegram, propuestas, aprobaciones y ejecutor.
No hay escaneos activos ni servidores supervisados. Mensajes guardados no ejecutan nada.

## Próximas tareas
1. Revisar e integrar la rama para preparar el despliegue. Pruebas reales PostgreSQL e imagen completadas en CI.
2. Configurar variables directamente en Easypanel, dominio HTTPS, puerto 8000 y desplegar con autorización.
3. Verificar persistencia después de reiniciar mike-app y configurar backups/retención.
4. Implementar monitoreo HTTP y scheduler; luego inspector SSH de operaciones permitidas.
5. Integrar OpenAI y Telegram con controles de identidad, contexto y alertas.
6. Implementar propuestas y aprobación de un solo uso antes de habilitar cualquier herramienta de escritura.

## Pendiente de inventario
OS, recursos, panel de Droplet piloto, mapeo de sitios/servidores, proxy/CDN, logs y backups.
