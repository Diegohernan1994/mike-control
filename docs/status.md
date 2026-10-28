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
10 pruebas API aprobadas con almacén de pruebas; 1 prueba real PostgreSQL omitida por falta de instancia de pruebas. JavaScript verificado con node --check. Sin Docker disponible: construcción de imagen no verificada. No se ha probado contra la base del propietario.

## Infraestructura informada por el propietario
Easypanel en DonWeb, separado de las Droplets supervisadas. Servicios mike-db y mike-app creados. Captura de PostgreSQL muestra listo para aceptar conexiones. Aplicación aún sin implementar; no se han recibido credenciales.

## No implementado
OpenAI y respuestas de agentes, memoria semántica/resúmenes, SSH, métricas, scheduler cada 15 minutos, incidentes, Telegram, propuestas, aprobaciones y ejecutor.
No hay escaneos activos ni servidores supervisados. Mensajes guardados no ejecutan nada.

## Próximas tareas
1. Revisar e integrar la rama y completar pruebas reales de PostgreSQL e imagen.
2. Configurar variables directamente en Easypanel, dominio HTTPS, puerto 8000 y desplegar con autorización.
3. Verificar persistencia después de reiniciar mike-app y configurar backups/retención.
4. Implementar monitoreo HTTP y scheduler; luego inspector SSH de operaciones permitidas.
5. Integrar OpenAI y Telegram con controles de identidad, contexto y alertas.
6. Implementar propuestas y aprobación de un solo uso antes de habilitar cualquier herramienta de escritura.

## Pendiente de inventario
OS, recursos, panel de Droplet piloto, mapeo de sitios/servidores, proxy/CDN, logs y backups.
