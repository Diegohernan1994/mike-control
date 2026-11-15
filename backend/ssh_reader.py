"""Strict read-only SSH adapter for WordPress servers.
Enforces pinned host key verification, explicit read-only commands (no arbitrary shell),
and blocks access to sensitive files (.env, wp-config.php, private keys, SQL dumps).
"""
import base64
import io
import posixpath
import shlex


def _paramiko():
    try:
        import paramiko
        return paramiko
    except ImportError:
        raise SSHError('Modulo paramiko no instalado en el servidor.', 500)

SSH_READ_ONLY_TOOLS = {
    'ssh_list_dir',
    'ssh_read_file',
    'ssh_search_code',
    'ssh_wp_verify_checksums',
}

BLOCKED_FILENAMES = {
    '.env',
    'wp-config.php',
    '.htpasswd',
    'id_rsa',
    'id_ed25519',
}
BLOCKED_EXTENSIONS = ('.pem', '.key', '.p12', '.pfx', '.sql', '.sqlite', '.bak')


class SSHError(Exception):
    def __init__(self, message, status_code=502):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def is_ssh_read_only_call(tool_name):
    return tool_name in SSH_READ_ONLY_TOOLS


def sanitize_ssh_rel_path(root_path, rel_path='', allow_empty=True):
    """Resolves a relative path safely inside root_path and blocks sensitive files."""
    if not root_path or not root_path.startswith('/'):
        raise SSHError('Ruta raiz SSH invalida.', 400)
    root = posixpath.normpath(root_path)
    raw = (rel_path or '').strip().replace('\\', '/').lstrip('/')
    if '\x00' in raw:
        raise SSHError('Ruta invalida.', 400)
    if not raw:
        if not allow_empty:
            raise SSHError('Debes indicar una ruta de archivo.', 400)
        return root
    parts = [p for p in raw.split('/') if p not in ('', '.')]
    if any(p == '..' for p in parts):
        raise SSHError('Path traversal bloqueado.', 403)
    filename = parts[-1].lower() if parts else ''
    if (
        filename in BLOCKED_FILENAMES
        or filename.startswith('.env.')
        or filename.endswith(BLOCKED_EXTENSIONS)
        or 'wp-config' in filename
    ):
        raise SSHError('Lectura bloqueada para archivos sensibles (wp-config, .env, llaves, dumps).', 403)
    joined = posixpath.normpath(posixpath.join(root, *parts))
    if joined != root and not joined.startswith(root.rstrip('/') + '/'):
        raise SSHError('Ruta fuera del directorio permitido.', 403)
    return joined


def _load_private_key(key_pem):
    paramiko = _paramiko()
    key_text = (key_pem or '').replace('\\n', '\n').strip()
    if not key_text:
        raise SSHError('Falta llave privada SSH en variables de entorno.', 400)
    for cls in (paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey):
        try:
            return cls.from_private_key(io.StringIO(key_text))
        except Exception:
            continue
    raise SSHError('Formato de llave privada SSH no soportado.', 400)


def _load_host_key(host_key_str):
    """Parses '<key-type> <base64>' into a Paramiko PKey for strict host pinning."""
    paramiko = _paramiko()
    parts = (host_key_str or '').strip().split()
    if len(parts) < 2:
        raise SSHError('Falta huella/clave publica del host SSH (verificacion obligatoria).', 400)
    ktype, b64_data = parts[0], parts[1]
    raw = base64.b64decode(b64_data)
    if ktype == 'ssh-ed25519':
        return paramiko.Ed25519Key(data=raw)
    if ktype == 'ssh-rsa':
        return paramiko.RSAKey(data=raw)
    if ktype.startswith('ecdsa-sha2-'):
        return paramiko.ECDSAKey(data=raw)
    raise SSHError(f'Tipo de host key SSH no soportado: {ktype}', 400)


def _run_readonly_command(ssh_config, command, timeout=20, max_bytes=32768):
    paramiko = _paramiko()
    host = (ssh_config or {}).get('host', '').strip()
    port = int((ssh_config or {}).get('port') or 22)
    username = (ssh_config or {}).get('username', '').strip()
    if not host or not username:
        raise SSHError('Configuracion SSH incompleta.', 400)

    pkey = _load_private_key(ssh_config.get('private_key', ''))
    expected_host_key = _load_host_key(ssh_config.get('host_key', ''))

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    host_entry = f'[{host}]:{port}' if port != 22 else host
    client.get_host_keys().add(host_entry, expected_host_key.get_name(), expected_host_key)

    try:
        client.connect(
            hostname=host,
            port=port,
            username=username,
            pkey=pkey,
            timeout=timeout,
            banner_timeout=timeout,
            auth_timeout=timeout,
            allow_agent=False,
            look_for_keys=False,
        )
        _, stdout, stderr = client.exec_command(command, timeout=timeout)
        out = stdout.read(max_bytes + 1).decode('utf-8', errors='replace')
        err = stderr.read(4096).decode('utf-8', errors='replace').strip()
        exit_code = stdout.channel.recv_exit_status()
        truncated = len(out) > max_bytes
        if truncated:
            out = out[:max_bytes]
        return {'exit_code': exit_code, 'stdout': out, 'stderr': err, 'truncated': truncated}
    except paramiko.SSHException as exc:
        raise SSHError(f'Error SSH (autenticacion o host key): {exc}', 502) from None
    except TimeoutError:
        raise SSHError('Tiempo de espera agotado en conexion SSH.', 504) from None
    except OSError:
        raise SSHError('No se pudo conectar al servidor por SSH.', 502) from None
    finally:
        client.close()


def execute_ssh_read_tool(ssh_config, tool_name, args=None):
    args = args or {}
    root = (ssh_config or {}).get('root_path', '').strip()

    if tool_name == 'ssh_list_dir':
        target = sanitize_ssh_rel_path(root, args.get('rel_path', ''), allow_empty=True)
        cmd = f'ls -la -- {shlex.quote(target)}'
        res = _run_readonly_command(ssh_config, cmd)
        # Filter sensitive filenames from directory output just in case
        filtered_lines = [
            line for line in res['stdout'].splitlines()
            if not any(b in line.lower() for b in ('wp-config', '.env', '.sql', '.pem', '.key', '.htpasswd'))
        ]
        return {'path': target, 'entries': '\n'.join(filtered_lines[:150]), 'stderr': res['stderr']}

    if tool_name == 'ssh_read_file':
        target = sanitize_ssh_rel_path(root, args.get('rel_path', ''), allow_empty=False)
        start = max(1, int(args.get('start_line') or 1))
        max_lines = min(200, max(1, int(args.get('max_lines') or 120)))
        end = start + max_lines - 1
        cmd = f"sed -n '{start},{end}p' -- {shlex.quote(target)}"
        res = _run_readonly_command(ssh_config, cmd)
        return {
            'path': target,
            'start_line': start,
            'end_line': end,
            'truncated': res['truncated'],
            'content': res['stdout'],
            'stderr': res['stderr'],
        }

    if tool_name == 'ssh_search_code':
        pattern = (args.get('pattern') or '').strip()
        if not pattern or len(pattern) > 100 or any(ord(c) < 32 for c in pattern):
            raise SSHError('Patron de busqueda invalido.', 400)
        target = sanitize_ssh_rel_path(root, args.get('rel_path', 'wp-content'), allow_empty=True)
        cmd = (
            "grep -rnI -m 50 -F "
            "--exclude='wp-config*' --exclude='.env*' --exclude='*.sql' --exclude='*.log' "
            f"-- {shlex.quote(pattern)} {shlex.quote(target)}"
        )
        res = _run_readonly_command(ssh_config, cmd)
        return {'path': target, 'pattern': pattern, 'matches': res['stdout'], 'truncated': res['truncated']}

    if tool_name == 'ssh_wp_verify_checksums':
        safe_root = sanitize_ssh_rel_path(root, '', allow_empty=True)
        cmd = f'wp --path={shlex.quote(safe_root)} core verify-checksums'
        res = _run_readonly_command(ssh_config, cmd, timeout=30)
        return {'root': safe_root, 'exit_code': res['exit_code'], 'output': res['stdout'], 'stderr': res['stderr']}

    raise SSHError(f'Herramienta SSH desconocida: {tool_name}', 400)


SSH_TOOLS_SCHEMA = [
    {
        'type': 'function',
        'name': 'ssh_list_dir',
        'description': 'Lista archivos y carpetas dentro del sitio WordPress por SSH (solo lectura).',
        'parameters': {
            'type': 'object',
            'properties': {
                'rel_path': {'type': 'string', 'description': 'Subcarpeta relativa, ej: wp-content/themes'},
            },
            'required': [],
        },
    },
    {
        'type': 'function',
        'name': 'ssh_read_file',
        'description': 'Lee lineas de un archivo del sitio WordPress por SSH (solo lectura; bloquea wp-config.php, .env, llaves y SQL).',
        'parameters': {
            'type': 'object',
            'properties': {
                'rel_path': {'type': 'string', 'description': 'Ruta relativa del archivo dentro del sitio.'},
                'start_line': {'type': 'integer', 'description': 'Linea inicial (1 por defecto).'},
                'max_lines': {'type': 'integer', 'description': 'Maximo de lineas a leer (hasta 200).'},
            },
            'required': ['rel_path'],
        },
    },
    {
        'type': 'function',
        'name': 'ssh_search_code',
        'description': 'Busca texto exacto en archivos del sitio WordPress por SSH (solo lectura).',
        'parameters': {
            'type': 'object',
            'properties': {
                'pattern': {'type': 'string', 'description': 'Texto exacto a buscar.'},
                'rel_path': {'type': 'string', 'description': 'Carpeta relativa donde buscar (por defecto wp-content).'},
            },
            'required': ['pattern'],
        },
    },
    {
        'type': 'function',
        'name': 'ssh_wp_verify_checksums',
        'description': 'Verifica integridad de archivos del core de WordPress usando WP-CLI (solo lectura).',
        'parameters': {'type': 'object', 'properties': {}, 'required': []},
    },
]
