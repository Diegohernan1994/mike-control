# Mike Control

Centro de supervisión con Mike y un agente por sitio. Primera entrega de backend: panel protegido y archivo de conversaciones en PostgreSQL.

**Chat con IA opcional y memoria reciente por agente.** Configurar OPENAI_API_KEY según [la guía de IA](docs/ai.md). Todavía no hay SSH, Telegram ni escaneos activos; los mensajes no ejecutan acciones.

## Instalación
Leer [la guía de Easypanel](docs/easypanel.md). La app requiere DATABASE_URL, ADMIN_USERNAME y ADMIN_PASSWORD (24+ caracteres). No hay credenciales por defecto. Configurar secretos directamente en el servidor, nunca en Git ni chats.

```sh
pip install -r requirements.lock
uvicorn backend.app:create_app --factory --host 127.0.0.1 --port 8000
```
Las variables deben estar en el entorno antes de iniciar. El backend crea su tabla en una base dedicada. Para Easypanel usar Dockerfile de la raíz y puerto interno 8000, con HTTPS en el proxy.

## Interfaz
- La aplicación real usa web/app.html y web/app.js y requiere backend.
- El prototipo original permanece en web/index.html; es una demo local sin autenticación ni integración. No desplegarlo como panel operativo.

## Continuidad
Leer [AGENTS.md](AGENTS.md), [requisitos](docs/requirements.md), [arquitectura](docs/architecture.md), [estado](docs/status.md) y [desarrollo](docs/development.md).
El código no configura despliegues automáticos. Los cambios remotos de sitios seguirán requiriendo autorización específica, implementada en un ejecutor futuro separado.

## Pruebas
```sh
pip install -r requirements-dev.txt
python -m pytest -q
```
La prueba de DB real requiere TEST_DATABASE_URL de una base desechable. Consultar las limitaciones de validación en docs/status.md.
