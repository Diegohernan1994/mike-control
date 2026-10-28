# Requisitos acordados

## Inventario y alcance
- 15 sitios WordPress en distintos proveedores: GoDaddy, SiteGround, DonWeb, DigitalOcean y Cloudways.
- Un Astro desplegado desde GitHub en Vercel, con Sanity mencionado en el alcance general. Pospuesto.
- Piloto: https://usbestroofing.com/ en DigitalOcean.
- Tres Droplets indicadas por el propietario, con accesos SSH independientes. Mapeo exacto de sitios/servidores pendiente.
- El propietario dispone de Easypanel y GitHub.
- No se han recibido credenciales ni se ha autorizado conectar un servidor concreto.

## Agentes y memoria
Mike coordina a los agentes individuales, reúne evidencias y se comunica con el propietario. Cada agente tiene herramientas e historial separados por sitio. Mike puede consultar los informes de todos.
Memoria duradera en PostgreSQL para configuración, incidentes, conversaciones, propuestas, autorizaciones y resultados. Recordar acciones no autoriza repetirlas.
Distinguir hechos, hipótesis y decisiones del propietario. Mantener estados propuesta/aprobada/rechazada/ejecutada/fallida/revertida y marcas de tiempo.
Definir retención, minimización de datos y backups antes del uso operativo.

## Monitoreo
Escaneo de lectura de cada sitio cada 15 minutos; mostrar inicio, fin, resultado, última medición y próxima ejecución. Evitar solapamientos y distribuir carga entre sitios.
Cubrir disponibilidad, HTTPS, velocidad, errores, RAM disponible, CPU, swap, disco/inodos, logs y señales de bots.
Una subida de tráfico no demuestra un ataque. Validar IP real cuando exista proxy/CDN.
OOM debe generar alerta crítica. Umbrales de recursos y latencia son configurables; valores definitivos dependen del inventario y línea base.
Formularios con efectos secundarios requieren autorización de pruebas.
La recolección ligera más frecuente fue sugerida, pero su frecuencia final no está acordada.

## Panel y Telegram
Interfaz minimalista inspirada en ChatGPT, con pestañas. Resumen por sitio, chat de Mike, chat individual por agente, incidentes, aprobaciones, memoria y configuración.
Mostrar estado desconocido/sin conectar cuando falten datos y distinguir datos vencidos de estado sano.
Alertas por Telegram y panel, deduplicación y aviso de recuperación.
Las autorizaciones desde ambos canales deben apuntar al mismo registro central.

## Ejecución
Inspección automática limitada a operaciones aprobadas al configurar el monitoreo.
Cambios de archivos, publicaciones, actualizaciones, bloqueos, reinicios y restauraciones requieren una orden específica. El ejecutor valida aprobación, alcance, vigencia y uso único.
Registrar evidencia, impacto, comprobación, plan de reversión y resultado. Un intento fallido no es un éxito.
