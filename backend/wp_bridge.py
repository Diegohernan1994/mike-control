"""HMAC-SHA256 signed connector to Ayrton Center WordPress Bridge.
Separates read-only inspection tools from write operations requiring owner approval.
"""
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class BridgeError(Exception):
    def __init__(self, message, status_code=502):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


READ_ONLY_TOOLS = {
    'wp_system_health_check',
    'wp_read_debug_log',
    'wp_inspect_url',
    'wp_get_site_overview',
    'wc_list_products',
    'wc_list_orders',
    'tutor_list_courses',
    'wp_list_pages',
    'wp_list_menus',
    'wp_list_plugins',
    'wp_recent_changes',
    'wp_get_activity_log',
}


def is_read_only_call(tool_name, args):
    """Strict allowlist: returns True only if the tool call has zero side effects."""
    if tool_name in READ_ONLY_TOOLS:
        return True
    if tool_name == 'tutor_diagnose_course':
        return not bool((args or {}).get('auto_fix', False))
    if tool_name == 'tutor_manage_enrollment':
        return (args or {}).get('action') == 'check'
    if tool_name == 'updraft_manage_backups':
        return (args or {}).get('action') == 'list'
    return False


def params_hash(tool_name, args):
    canonical = json.dumps({'tool': tool_name, 'args': args or {}}, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def execute_remote_tool(site_url, bridge_secret, tool_name, args=None, timeout=45):
    """Calls /wp-json/ayrton-center/v1/remote-execute with HMAC-SHA256 signature."""
    if not site_url or not bridge_secret:
        raise BridgeError('El sitio no tiene configurado URL o Bridge Secret.', 400)

    endpoint = site_url.rstrip('/') + '/wp-json/ayrton-center/v1/remote-execute'
    payload = json.dumps({'tool': tool_name, 'args': args or {}}, ensure_ascii=True)
    timestamp = str(int(time.time()))
    sig_input = f'{timestamp}.{payload}'.encode('utf-8')
    signature = hmac.new(bridge_secret.encode('utf-8'), sig_input, hashlib.sha256).hexdigest()

    request = urllib.request.Request(
        endpoint,
        data=payload.encode('utf-8'),
        method='POST',
        headers={
            'Content-Type': 'application/json',
            'X-Ayrton-Timestamp': timestamp,
            'X-Ayrton-Signature': signature,
        },
    )
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as resp:
            raw = resp.read(524288)
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise BridgeError('Respuesta invalida del conector WordPress.')
        return data
    except urllib.error.HTTPError as exc:
        raise BridgeError(f'WordPress Bridge HTTP {exc.code}', exc.code) from None
    except TimeoutError:
        raise BridgeError('Tiempo de espera agotado al conectar con WordPress.', 504) from None
    except urllib.error.URLError:
        raise BridgeError('No se pudo conectar con el servidor WordPress.', 502) from None
    except Exception:
        raise BridgeError('Error inesperado al ejecutar herramienta remota.', 500) from None


WP_TOOLS_SCHEMA = [
    {
        'type': 'function',
        'name': 'wp_get_site_overview',
        'description': 'Resumen general del sitio WordPress (version, tema, WooCommerce, Tutor LMS, conteos). Solo lectura.',
        'parameters': {'type': 'object', 'properties': {}, 'required': []},
    },
    {
        'type': 'function',
        'name': 'wp_system_health_check',
        'description': 'Diagnostico de salud tecnica: PHP, memoria, SSL, paginas obligatorias de WooCommerce y Tutor LMS. Solo lectura.',
        'parameters': {'type': 'object', 'properties': {}, 'required': []},
    },
    {
        'type': 'function',
        'name': 'wp_read_debug_log',
        'description': 'Lee las ultimas lineas de debug.log de WordPress para diagnosticar errores PHP. Solo lectura.',
        'parameters': {
            'type': 'object',
            'properties': {'lines': {'type': 'integer', 'description': 'Cantidad de lineas (max 100)'}},
        },
    },
    {
        'type': 'function',
        'name': 'wp_inspect_url',
        'description': 'Inspecciona una URL interna del sitio para comprobar codigo HTTP (200/404/500) y errores criticos. Solo lectura.',
        'parameters': {
            'type': 'object',
            'properties': {'url': {'type': 'string'}},
            'required': ['url'],
        },
    },
    {
        'type': 'function',
        'name': 'wp_maintenance_repair',
        'description': 'ESCRITURA (requiere aprobacion): Regenera enlaces permanentes (404) o purga caches y CSS de Elementor.',
        'parameters': {
            'type': 'object',
            'properties': {'action': {'type': 'string', 'enum': ['flush_permalinks', 'clear_cache', 'full_repair']}},
            'required': ['action'],
        },
    },
    {
        'type': 'function',
        'name': 'updraft_manage_backups',
        'description': 'Gestiona copias de seguridad de UpdraftPlus: list es solo lectura; create y delete requieren aprobacion.',
        'parameters': {
            'type': 'object',
            'properties': {
                'action': {'type': 'string', 'enum': ['list', 'create', 'delete']},
                'backup_type': {'type': 'string', 'enum': ['db', 'all']},
                'timestamp': {'type': 'string'},
            },
            'required': ['action'],
        },
    },
    {
        'type': 'function',
        'name': 'wc_list_products',
        'description': 'Lista o busca productos en WooCommerce. Solo lectura.',
        'parameters': {
            'type': 'object',
            'properties': {
                'search': {'type': 'string'},
                'limit': {'type': 'integer'},
                'status': {'type': 'string'},
            },
        },
    },
    {
        'type': 'function',
        'name': 'wc_create_product',
        'description': 'ESCRITURA (requiere aprobacion): Crea un producto simple en WooCommerce.',
        'parameters': {
            'type': 'object',
            'properties': {
                'name': {'type': 'string'},
                'regular_price': {'type': 'string'},
                'sale_price': {'type': 'string'},
                'description': {'type': 'string'},
                'short_description': {'type': 'string'},
                'sku': {'type': 'string'},
                'stock_quantity': {'type': 'integer'},
            },
            'required': ['name', 'regular_price'],
        },
    },
    {
        'type': 'function',
        'name': 'wc_update_product',
        'description': 'ESCRITURA (requiere aprobacion): Modifica campos de un producto existente de WooCommerce.',
        'parameters': {
            'type': 'object',
            'properties': {
                'product_id_or_name': {'type': 'string'},
                'name': {'type': 'string'},
                'regular_price': {'type': 'string'},
                'sale_price': {'type': 'string'},
                'stock_quantity': {'type': 'integer'},
                'status': {'type': 'string'},
            },
            'required': ['product_id_or_name'],
        },
    },
    {
        'type': 'function',
        'name': 'wc_list_orders',
        'description': 'Lista los pedidos recientes de WooCommerce. Solo lectura.',
        'parameters': {
            'type': 'object',
            'properties': {'limit': {'type': 'integer'}, 'status': {'type': 'string'}},
        },
    },
    {
        'type': 'function',
        'name': 'wc_update_order_status',
        'description': 'ESCRITURA (requiere aprobacion): Cambia el estado de un pedido WooCommerce.',
        'parameters': {
            'type': 'object',
            'properties': {'order_id': {'type': 'integer'}, 'new_status': {'type': 'string'}},
            'required': ['order_id', 'new_status'],
        },
    },
    {
        'type': 'function',
        'name': 'tutor_list_courses',
        'description': 'Lista los cursos de Tutor LMS. Solo lectura.',
        'parameters': {
            'type': 'object',
            'properties': {'search': {'type': 'string'}, 'status': {'type': 'string'}, 'limit': {'type': 'integer'}},
        },
    },
    {
        'type': 'function',
        'name': 'tutor_diagnose_course',
        'description': 'Diagnostica fallos de un curso Tutor LMS (auto_fix=false es lectura; auto_fix=true requiere aprobacion).',
        'parameters': {
            'type': 'object',
            'properties': {
                'course_id_or_title': {'type': 'string'},
                'auto_fix': {'type': 'boolean'},
            },
            'required': ['course_id_or_title'],
        },
    },
    {
        'type': 'function',
        'name': 'tutor_manage_enrollment',
        'description': 'Gestiona matriculas de alumnos en Tutor LMS (check es lectura; enroll/unenroll requieren aprobacion).',
        'parameters': {
            'type': 'object',
            'properties': {
                'user_email': {'type': 'string'},
                'action': {'type': 'string', 'enum': ['check', 'enroll', 'unenroll']},
                'course_id_or_title': {'type': 'string'},
            },
            'required': ['user_email', 'action'],
        },
    },
    {
        'type': 'function',
        'name': 'tutor_update_course',
        'description': 'ESCRITURA (requiere aprobacion): Publica, oculta o edita un curso de Tutor LMS.',
        'parameters': {
            'type': 'object',
            'properties': {
                'course_id_or_title': {'type': 'string'},
                'title': {'type': 'string'},
                'status': {'type': 'string'},
                'price': {'type': 'string'},
            },
            'required': ['course_id_or_title'],
        },
    },
    {
        'type': 'function',
        'name': 'wp_list_pages',
        'description': 'Lista paginas de WordPress. Solo lectura.',
        'parameters': {
            'type': 'object',
            'properties': {'search': {'type': 'string'}, 'limit': {'type': 'integer'}},
        },
    },
    {
        'type': 'function',
        'name': 'wp_list_plugins',
        'description': 'Lista plugins instalados y su estado activo/inactivo. Solo lectura.',
        'parameters': {'type': 'object', 'properties': {}, 'required': []},
    },
    {
        'type': 'function',
        'name': 'wp_toggle_plugin',
        'description': 'ESCRITURA (requiere aprobacion): Activa o desactiva un plugin de WordPress.',
        'parameters': {
            'type': 'object',
            'properties': {
                'plugin_search_or_slug': {'type': 'string'},
                'action': {'type': 'string', 'enum': ['activate', 'deactivate']},
            },
            'required': ['plugin_search_or_slug', 'action'],
        },
    },
    {
        'type': 'function',
        'name': 'wp_recent_changes',
        'description': 'Consulta retroactiva de cambios recientes en WordPress (contenido modificado, usuarios creados y archivos modificados en temas/plugins). Solo lectura.',
        'parameters': {
            'type': 'object',
            'properties': {
                'days': {'type': 'integer', 'description': 'Dias hacia atras (1 a 30, defecto 7).'},
                'limit': {'type': 'integer', 'description': 'Maximo por categoria (1 a 50, defecto 20).'},
                'include_files': {'type': 'boolean', 'description': 'Incluir escaneo de mtime en temas/plugins.'},
            },
        },
    },
    {
        'type': 'function',
        'name': 'wp_get_activity_log',
        'description': 'Consulta la bitacora de auditoria en tiempo real de Ayrton Center (ediciones, plugins/temas, usuarios, logins y opciones criticas). Solo lectura.',
        'parameters': {
            'type': 'object',
            'properties': {
                'days': {'type': 'integer', 'description': 'Dias hacia atras (1 a 90, defecto 7).'},
                'category': {'type': 'string', 'enum': ['all', 'content', 'plugins', 'users', 'auth', 'options']},
                'limit': {'type': 'integer', 'description': 'Maximo de eventos (1 a 100, defecto 40).'},
            },
        },
    },
]
