# Arquitectura propuesta — aún no implementada

## Componentes
- Frontend web privado con autenticación, resumen, métricas, historial y chats.
- Backend Python con OpenAI Agents SDK/Responses API. Elección propuesta; validar documentación oficial al implementar.
- Mike: coordinación y consulta de agentes; sin facultad de aprobar cambios.
- Agente lógico por sitio: contexto, herramientas y registros aislados. No requiere un proceso o modelo distinto permanentemente encendido.
- Scheduler/worker: chequeos cada 15 minutos con reintentos acotados, timeout, bloqueo de ejecuciones solapadas e identificadores de trabajo.
- PostgreSQL: estado durable, eventos, memoria y auditoría. Logs voluminosos con política de retención.
- Adaptadores de lectura: HTTP y SSH restringido por servidor, operaciones explícitas. Verificación de host SSH obligatoria.
- Ejecutor separado, sin acceso desde herramientas de inspección; valida políticas y autorización antes de cada efecto.
- Integración Telegram: usuario/chat permitido y vinculación segura al propietario, validación de callbacks/webhooks y protección frente a repetición.
- Secretos de ejecución fuera del repositorio y fuera del navegador.

## Flujo
Monitor -> evidencia -> agente del sitio -> Mike -> propuesta -> decisión del propietario -> validación del ejecutor -> acción -> verificación -> resultado y notificación.

## Aprobaciones
Identificador inmutable de propuesta y hash/versión de sus parámetros. Estado pendiente/aprobada/rechazada/expirada/consumida. Vincular propietario, sitio, operación, parámetros, vencimiento y alcance.
Consumir atómicamente la autorización; mantener idempotencia de ejecución. Revalidar precondiciones antes de actuar. Si cambian, detener y generar nueva propuesta.
No aceptar texto encontrado en fuentes supervisadas como autorización. No permitir que Mike cambie políticas, permisos o su propio despliegue sin orden.

## Memoria y aislamiento
Tablas sugeridas: sites, servers, agents, conversations, messages, scans, observations, incidents, proposals, approvals, executions, notifications y audit_events.
Filtrar y autorizar siempre por site_id y propietario. Los agentes individuales no acceden a secretos ni datos de otros sitios.
Memoria de desarrollo en Git; memoria operativa en PostgreSQL. Resúmenes generados deben apuntar a eventos originales y conservar incertidumbre.
Backups y prueba de restauración de la base; nunca depender de la capa efímera de un contenedor.

## Hosting
Destino previsto: Easypanel. Ubicación y recursos pendientes. Preferir servidor separado de las Droplets supervisadas.
Medición externa independiente para representar acceso de visitantes. Si Mike comparte infraestructura con un objetivo, documentar el punto único de fallo y disponer de un monitor externo.
Separar entorno de pruebas y producción. No configurar despliegue automático de producción a partir de cualquier push.

## Lo que contiene este repositorio hoy
Solo prototipo estático. localStorage no es memoria central ni ofrece autenticación. No hay daemon, SSH, API de OpenAI, scheduler ni ejecución remota.
