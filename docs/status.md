# Estado — 2026-10-28

## Disponible
- Prototipo original transferido a web/index.html.
- Resumen, pestañas de incidentes/aprobaciones/memoria/configuración.
- Chat simulado de Mike y por agente; mensajes locales al navegador.
- Estados sin conexión y frecuencia prevista de 15 minutos.
- Documentación del alcance y restricciones.

## No implementado
Autenticación propia, backend, PostgreSQL, memoria central, OpenAI, conexiones SSH, métricas, scheduler, alertas Telegram, propuestas reales y ejecutor con aprobaciones.
No hay servidores conectados, escaneos activos ni despliegue en Easypanel.

## Datos pendientes
- Dónde está Easypanel y recursos disponibles.
- Sistema operativo, panel y recursos de la Droplet piloto.
- Mapeo de los tres servidores y sitios que alojan.
- Proxy/CDN, servidor web, ubicación de logs y backups.
- Dominio privado para el panel.
- Configuración segura de SSH, OpenAI y Telegram cuando corresponda; no pedir secretos por chat.

## Próximas entregas
1. Revisar e integrar esta base.
2. Crear backend con autenticación, esquema PostgreSQL y persistencia de conversaciones.
3. Implementar monitoreo HTTP de lectura y scheduler cada 15 minutos; sin declarar activo hasta verificar.
4. Preparar y revisar el acceso SSH restringido al piloto.
5. Integrar alertas Telegram con identidad verificada y deduplicación.
6. Implementar propuestas y aprobaciones de un solo uso, probadas antes de habilitar escritura.
7. Preparar despliegue revisable en Easypanel y realizarlo cuando se autorice.

## Validación
La interfaz original se abrió en navegador y se verificó navegación al chat de Mike. Para esta transferencia se verifica que el HTML es idéntico al prototipo y que su JavaScript compila. No equivale a validar servicios operativos.
