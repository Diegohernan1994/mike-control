# Chat con memoria reciente

Agregar OPENAI_API_KEY en las variables de entorno de mike-app. No escribirla en chats, GitHub, capturas o archivos públicos. OPENAI_MODEL es opcional y usa gpt-5-mini por defecto. El proyecto de OpenAI necesita acceso al modelo y facturación disponible. Guardar las variables y desplegar la versión que contiene esta integración.

La configuración se indica como «configurado», no como conexión comprobada. Enviar un mensaje verifica la API. Cada envío es una solicitud facturable; no hay llamadas en segundo plano ni reintentos automáticos. No se probaron credenciales reales durante el desarrollo.

El backend llama a https://api.openai.com/v1/responses con store=false, sin herramientas. Esto desactiva el almacenamiento de respuestas para recuperación por API; no constituye una garantía de retención cero del proveedor. Se transmite únicamente el fragmento reciente del chat elegido: hasta 40 mensajes y 24.000 caracteres. PostgreSQL conserva el historial; la interfaz consulta los últimos 100 mensajes. No existe aún recuperación de recuerdos antiguos ni memoria semántica. Mike todavía no consulta otros chats.

Respuesta limitada a 2048 tokens, lectura de respuesta hasta 256 KiB y timeout de socket de 45 segundos. Un resultado incompleto o sin texto genera un aviso, nunca una respuesta fingida. El usuario queda guardado incluso si la API falla. Para continuar, enviar otro mensaje; no existe reintento automático. Si se pierde la conexión del navegador, consultar el historial antes de reenviar para evitar duplicados.

Usar UNA réplica y UN worker como en el Dockerfile: el bloqueo de envíos simultáneos por chat es local al proceso. Escalar requiere bloqueo e idempotencia distribuida. Reiniciar durante una solicitud puede dejar el mensaje sin respuesta; no se reanuda automáticamente.

La migración de inicio amplía el CHECK de roles a assistant dentro de una transacción y conserva los mensajes existentes. Hacer backup de PostgreSQL antes del despliegue. No volver a la versión antigua sin adaptar su validación de roles.

Prueba de instalación: decir «Recordá que mi color de prueba es azul», esperar respuesta, recargar y preguntar por ese color. En el chat del otro agente no debe aparecer ese historial. Solicitar un reinicio de servidor debe producir solo conversación: no existe ejecutor.

Fuentes: https://developers.openai.com/api/docs/guides/text y https://developers.openai.com/api/docs/models/gpt-5-mini
