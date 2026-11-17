# Estado — 2026-10-28

## Informes diarios preparados — 2026-11-17
El propietario pidió un diagnóstico diario de cada agente a las 08:00 de Argentina. Rama `codex/daily-reports`: scheduler dentro de la aplicación, con `America/Argentina/Buenos_Aires` y comprobación cada 30 segundos. Se habilita por defecto al cargar la configuración del servidor si OpenAI está configurado; `DAILY_REPORTS_ENABLED=false` lo desactiva.

Se reutiliza la herramienta de informes de lectura a todos los sitios activos. Guarda las respuestas en cada chat de agente y reúne los resultados, en partes de menos de 8000 caracteres cuando es necesario, en Chat con Mike. La recopilación es determinista y no agrega llamadas a OpenAI. Los sitios sin conexión o agentes ocupados/fallidos se indican explícitamente. Configuración muestra horario y última ejecución.

La tabla `daily_reports` registra una única ejecución por fecha argentina mediante clave primaria e inserción atómica. La publicación de resultados en Mike y la finalización de la ejecución comparten una transacción. Si un informe falla o el proceso se interrumpe después de reclamar la fecha, se conservan los mensajes ya guardados y ese día no se vuelve a gastar API automáticamente. Los registros de días anteriores que quedaron en ejecución se marcan como interrumpidos en la siguiente comprobación. Si el servidor arranca después de las 08:00 y ese día aún no se había iniciado el informe, lo genera al arrancar. Una conversación activa con Mike pospone el inicio hasta que quede libre.

Validación local: 73 pruebas aprobadas y 4 pruebas de PostgreSQL omitidas por falta de una base desechable local. JavaScript válido y comprobación con DOM/API simulados de la tarjeta del horario y última ejecución. PostgreSQL y Docker se verifican en CI. Pendiente revisión, integración y despliegue con autorización. La generación consume la API configurada por los informes de los agentes. La comprobación final requiere los conectores reales después de desplegar.

## Corrección preparada — 2026-11-17
El propietario compartió un fallo genérico del panel al pedir informes de todos los agentes. Los registros aportados muestran arranques y cierres ordenados, sin excepción asociada al pedido. La causa del fallo en producción y de los reinicios queda sin confirmar.

Rama `codex/report-background`: el panel envía mensajes con `background=true` y recibe HTTP 202 después de guardarlos. Consulta el estado de la respuesta mediante solicitudes cortas, evitando mantener una sola solicitud web abierta durante todas las consultas. Conserva el contrato síncrono para los clientes existentes. Al volver al chat o recargar, retoma la consulta de una respuesta activa.

Los estados de trabajos y bloqueos viven en el proceso único configurado por Dockerfile. Un reinicio interrumpe las respuestas activas y pierde esos estados; el historial ya guardado permanece en PostgreSQL. El panel que estaba esperando recibe un aviso de interrupción. Los trabajos terminados caducan de memoria al cabo de una hora. Esta entrega no implementa una cola durable ni reintentos automáticos.

Nueva herramienta `mike_ask_all_agents`: solicita informes de lectura para todos los sitios activos, con un máximo de tres agentes simultáneos. Devuelve un resultado por sitio, incluyendo ocupados, fallidos y sin conexión. Guarda los pedidos y respuestas de agentes conectados en sus chats. El modo de informe impide crear propuestas de escritura. Se conserva la salida completa de Responses API, incluidos los elementos de razonamiento, al continuar después de llamadas a herramientas.

Los errores inesperados de procesamiento muestran una referencia y registran tipo y ubicaciones de código sin valores de excepciones. Validación automatizada cubre recepción inmediata, recuperación de estado al recargar, aislamiento, bloqueo de envíos simultáneos, fallos seguros, cobertura de todos los agentes y restricciones de lectura. Pendiente integrar y desplegar con autorización, y comprobar el pedido con los conectores reales del propietario.

Validación local de esta corrección: 68 pruebas aprobadas y 3 pruebas de PostgreSQL omitidas por falta de base desechable local. JavaScript válido y comprobación con DOM/API simulados de envío, consulta de estado, actualización del historial y cambio de chat. PostgreSQL real y Docker se verifican en GitHub Actions antes de integrar.

## Preparación local — 2026-11-04
El propietario verificó respuestas en el panel y acceso a gpt-6.1-sol con la clave de Mike; la variable OPENAI_MODEL del servicio muestra ese modelo. Preparado localmente un chequeo GET de disponibilidad para US Best Roofing cada 15 minutos, con resultado persistente. Está desactivado por defecto y requiere MONITOR_ENABLED=true y despliegue autorizado; esta modificación no ha sido desplegada. El chat no accede aún a los resultados, no hay alertas, SSH ni diagnóstico automático. HTTP exitoso no verifica formularios ni funcionamiento visual. Los redireccionamientos se registran sin seguirlos. Confirmar respaldos y probar la migración de base antes de desplegar.

## Base desplegada
El propietario confirmó que mike.gdtwo.com funciona en Easypanel y PostgreSQL figura conectado. El panel base conserva conversaciones separadas. No se recibieron sus credenciales.

## Segunda entrega: rama codex/chat-memory
Implementada integración opcional Responses API para Mike y US Best Roofing, con historial reciente aislado, respuestas guardadas, indicador de espera y aviso de fallos. Clave solo en servidor. Migración transaccional agrega rol assistant sin borrar mensajes. Configuración en docs/ai.md.

Pruebas incluidas: API autenticada, aislamiento, persistencia de assistant después de reinicializar PostgreSQL, contexto limitado, solicitudes simultáneas, errores y contrato HTTP con proveedor simulado. Validación de PostgreSQL y Docker mediante el workflow Verify backend and Docker. No se realizó ninguna llamada con una clave real; la comprobación final de OpenAI queda para el despliegue autorizado.

## Pendiente
Integrar y desplegar esta segunda entrega con autorización. Backups y retención de PostgreSQL. Monitoreo HTTP/SSH cada 15 minutos, métricas, detección de bots, Telegram, memoria de incidentes y resúmenes, propuestas y ejecución con aprobación específica. Ningún servidor está siendo inspeccionado y ningún chat ejecuta comandos.

## Diagnóstico del primer intento real
El propietario desplegó la segunda entrega y compartió un aviso de fallo genérico al llamar a OpenAI. La causa real aún no está identificada. Rama codex/ai-diagnostics: diagnósticos acotados para autenticación, cuota, permisos, modelo, solicitudes, conexión, timeout y respuestas incompletas. Nunca se muestran cuerpos de error, claves ni mensajes del proveedor. Pruebas locales: 33 aprobadas; PostgreSQL y Docker se verifican en CI. No se cambiaron credenciales, modelo ni presupuesto de tokens por conjetura.
