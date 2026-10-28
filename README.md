# Mike Control

Panel y sistema de supervisión de sitios con Mike como coordinador y un agente por sitio.

## Estado actual
Prototipo estático navegable, sin backend ni conexiones reales. Los chats responden con mensajes de demostración y guardan su historial únicamente en localStorage de este navegador. No hay IA, PostgreSQL, SSH, Telegram ni escaneos activos. No ingresar credenciales.

## Ejecutar el prototipo
Abrir `web/index.html` en un navegador. Para servirlo localmente, con Python instalado:
```sh
python -m http.server 8080 --directory web --bind 127.0.0.1
```
Visitar http://localhost:8080. Este servidor es para desarrollo.

## Documentación
- [Reglas para Codex](AGENTS.md)
- [Requisitos](docs/requirements.md)
- [Arquitectura propuesta](docs/architecture.md)
- [Estado y próximos pasos](docs/status.md)
- [Continuar en Codex](docs/development.md)

## Desarrollo y despliegue
GitHub es la fuente del código. Trabajar en ramas y revisar propuestas antes de integrar. No hay automatizaciones de despliegue. Easypanel es el destino previsto, todavía sin configurar.
Las credenciales nunca se guardan en Git. La memoria operativa irá en PostgreSQL, separada del repositorio.
