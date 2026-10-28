# Continuar con Codex

Abrir el repositorio como proyecto local independiente. Leer AGENTS.md y docs/status.md.

Para revisar esta entrega sin integrar aún:
```
git fetch origin
git switch --track origin/codex/initial-panel
```
Si la rama ya existe localmente, usar git switch codex/initial-panel y revisar cambios antes de actualizar. No sobrescribir archivos locales. La conversación externa no se sincroniza automáticamente.

## Estado de implementación
Backend base en backend/app.py; panel conectado al archivo de conversaciones en web/app.html y web/app.js. Dockerfile en raíz, puerto 8000. El prototipo original sigue en web/index.html.
Instalación y verificaciones pendientes en docs/easypanel.md. Las dependencias efectivamente probadas están fijadas en requirements.lock. requirements.txt expresa los rangos de actualización; cualquier actualización debe regenerar el lock y repetir pruebas.

## Siguiente tarea
Completar integración real de PostgreSQL y construcción de la imagen. No declarar listo para producción sin esas pruebas y HTTPS/acceso configurados.
Después implementar monitoreo de lectura y scheduler, OpenAI, Telegram y aprobaciones según docs/requirements.md. Cualquier implementación de API OpenAI debe consultar documentación oficial vigente antes de empezar.

Trabajar en ramas y pull requests. No fusionar ni desplegar sin orden explícita. No hay workflow de despliegue automático ni SSH disponible. La memoria operativa será PostgreSQL, no Git.
