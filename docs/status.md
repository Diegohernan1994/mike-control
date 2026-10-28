# Estado — 2026-10-28

## Base desplegada
El propietario confirmó que mike.gdtwo.com funciona en Easypanel y PostgreSQL figura conectado. El panel base conserva conversaciones separadas. No se recibieron sus credenciales.

## Segunda entrega: rama codex/chat-memory
Implementada integración opcional Responses API para Mike y US Best Roofing, con historial reciente aislado, respuestas guardadas, indicador de espera y aviso de fallos. Clave solo en servidor. Migración transaccional agrega rol assistant sin borrar mensajes. Configuración en docs/ai.md.

Pruebas incluidas: API autenticada, aislamiento, persistencia de assistant después de reinicializar PostgreSQL, contexto limitado, solicitudes simultáneas, errores y contrato HTTP con proveedor simulado. Validación de PostgreSQL y Docker mediante el workflow Verify backend and Docker. No se realizó ninguna llamada con una clave real; la comprobación final de OpenAI queda para el despliegue autorizado.

## Pendiente
Integrar y desplegar esta segunda entrega con autorización. Backups y retención de PostgreSQL. Monitoreo HTTP/SSH cada 15 minutos, métricas, detección de bots, Telegram, memoria de incidentes y resúmenes, propuestas y ejecución con aprobación específica. Ningún servidor está siendo inspeccionado y ningún chat ejecuta comandos.

## Diagnóstico del primer intento real
El propietario desplegó la segunda entrega y compartió un aviso de fallo genérico al llamar a OpenAI. La causa real aún no está identificada. Rama codex/ai-diagnostics: diagnósticos acotados para autenticación, cuota, permisos, modelo, solicitudes, conexión, timeout y respuestas incompletas. Nunca se muestran cuerpos de error, claves ni mensajes del proveedor. Pruebas locales: 33 aprobadas; PostgreSQL y Docker se verifican en CI. No se cambiaron credenciales, modelo ni presupuesto de tokens por conjetura.
