# Continuar con Codex

## Abrir el código
Clonar el repositorio y abrir su carpeta como proyecto local independiente de otros proyectos.
Para revisar esta entrega antes de integrarla:
```sh
git fetch origin
git switch --track origin/codex/initial-panel
```
Si ya existe una rama local con ese nombre, usar git switch codex/initial-panel y revisar el estado antes de actualizar.
Leer AGENTS.md y docs/status.md al comenzar una sesión. La conversación externa no se sincroniza automáticamente.

## Próxima tarea sugerida
Revisar el prototipo y proponer la primera entrega de backend: autenticación, base PostgreSQL y persistencia de chats. Mantener monitoreo remoto y escritura deshabilitados. Validar documentación oficial de dependencias antes de implementarlas.

## Sincronización
Cambios en ramas, commits explícitos y pull requests. Revisar y probar antes de integrar. No hacer force push ni sobrescribir trabajo ajeno.
GitHub conserva código y decisiones de desarrollo; PostgreSQL conservará memoria operativa.
No hay workflow de despliegue ni conexión configurada a Easypanel.
