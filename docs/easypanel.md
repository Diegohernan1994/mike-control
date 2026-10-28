# Primera instalación en Easypanel

## Alcance de esta entrega
Backend para acceso privado y archivo de conversaciones en PostgreSQL. Todavía NO incluye IA, SSH, Telegram, monitoreo, propuestas ni ejecución. Guardar un mensaje no envía una orden ni crea una respuesta de Mike.
El prototipo anterior permanece en web/index.html, pero el backend sirve web/app.html y web/app.js. Los mensajes de la demo local no se importan automáticamente.

## Preparar código
Revisar e integrar el pull request antes de desplegar main. Alternativamente usar la rama codex/initial-panel solo en un entorno de pruebas. No asumir que main ya tiene Dockerfile.
Fuente: Diegohernan1994/mike-control, ruta de compilación /, Dockerfile en la raíz.

## Base de datos
Usar mike-db por la red interna de Easypanel. Copiar la conexión interna de su configuración directamente al campo DATABASE_URL de mike-app, sin pegarla en chats ni guardarla en Git. No inventar el hostname: usar el que informa Easypanel.
La app crea su tabla conversation_messages y su índice al arrancar; no elimina tablas ni datos. Usar una base dedicada al proyecto, no una base de un sitio existente. El usuario requiere permisos para crear su tabla y leer/escribir en ella.
PostgreSQL debe tener un volumen persistente y backups configurados; verificar una restauración antes de depender de esta memoria. No se configuraron backups desde este repositorio.

## Variables de mike-app
- DATABASE_URL: URI o conninfo de PostgreSQL proporcionado por el panel. Si se arma una URI manualmente, codificar caracteres especiales de usuario/contraseña. Preferir copiar la cadena interna ya formada.
- ADMIN_USERNAME: usuario privado del propietario.
- ADMIN_PASSWORD: contraseña aleatoria única de al menos 24 caracteres. No existe una contraseña predeterminada.
No cargar claves de OpenAI, Telegram ni SSH todavía: esta entrega no las utiliza.

## Red y acceso
Puerto interno de aplicación: 8000. Configurar dominio con HTTPS en el proxy de Easypanel. No publicar el puerto 8000 directamente en Internet ni exponer PostgreSQL. Antes de ingresar credenciales, comprobar HTTPS válido.
La primera entrega usa HTTP Basic para un único propietario; el navegador muestra un diálogo de acceso y puede conservar credenciales hasta cerrar su sesión. No es un sistema multiusuario ni tiene MFA. Limitar inicialmente el acceso al piloto mediante VPN o allowlist si está disponible; implementar control de intentos en el proxy antes de exposición general.

## Comprobación posterior al despliegue
1. Revisar logs: Uvicorn iniciado en 0.0.0.0:8000. No compartir variables o cadenas de conexión en capturas.
2. Abrir el dominio HTTPS: debe pedir usuario y contraseña.
3. Verificar Resumen: PostgreSQL conectado, sitio sin mediciones y escaneo aún no implementado.
4. Guardar un mensaje de prueba en Mike y otro en el agente. Recargar y comprobar que permanecen separados.
5. Reiniciar únicamente mike-app y volver a consultar los mensajes: deben persistir.
6. GET /health/live comprueba proceso, no base; GET /health/ready requiere autenticación y prueba PostgreSQL. El healthcheck de Docker es de vida, no de disponibilidad de DB.
Si DB no está disponible al iniciar, la app falla sin habilitar un modo temporal sin persistencia. Corregir configuración y volver a iniciar.

## Validación local de esta entrega
10 pruebas de API aprobadas con un almacén de pruebas: acceso, protección frente a escrituras de otros orígenes, límites, aislamiento, estados y errores sin secretos. JavaScript compilado con node --check.
La prueba de PostgreSQL real está incluida, pero no ejecutada aquí por no haber una instancia de pruebas disponible. Docker no está disponible en este entorno: no se verificó docker build. Estas verificaciones deben completarse antes de considerar validado el despliegue.

Para reproducir:
```
python -m venv .venv
# Activar el entorno según el sistema operativo.
pip install -r requirements.lock -r requirements-dev.txt
python -m pytest -q
```
La prueba real se activa con TEST_DATABASE_URL apuntando exclusivamente a una base aislada de pruebas. Crea tabla/índice y elimina solo sus mensajes de prueba; no usar contra una base de producción.
