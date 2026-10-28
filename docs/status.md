# Estado — 2026-10-28

## Base desplegada
El propietario confirmó que mike.gdtwo.com funciona en Easypanel y PostgreSQL figura conectado. El panel base conserva conversaciones separadas. No se recibieron sus credenciales.

## Segunda entrega: rama codex/chat-memory
Implementada integración opcional Responses API para Mike y US Best Roofing, con historial reciente aislado, respuestas guardadas, indicador de espera y aviso de fallos. Clave solo en servidor. Migración transaccional agrega rol assistant sin borrar mensajes. Configuración en docs/ai.md.

Pruebas incluidas: API autenticada, aislamiento, persistencia de assistant después de reinicializar PostgreSQL, contexto limitado, solicitudes simultáneas, errores y contrato HTTP con proveedor simulado. Validación de PostgreSQL y Docker mediante el workflow Verify backend and Docker. No se realizó ninguna llamada con una clave real; la comprobación final de OpenAI queda para el despliegue autorizado.

## Pendiente
Integrar y desplegar esta segunda entrega con autorización. Backups y retención de PostgreSQL. Monitoreo HTTP/SSH cada 15 minutos, métricas, detección de bots, Telegram, memoria de incidentes y resúmenes, propuestas y ejecución con aprobación específica. Ningún servidor está siendo inspeccionado y ningún chat ejecuta comandos.
