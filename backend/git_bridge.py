"""GitHub + Vercel GitOps connector for Astro / Node / React sites.
Read-only inspection runs directly; file changes and PR merges require owner approval
and always target a feature branch + Pull Request (never direct push to main).
"""
import base64
import json
import re
import urllib.error
import urllib.parse
import urllib.request

REPO_RE = re.compile(r'^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$')
SENSITIVE_FILENAMES = {
    '.env',
    'id_rsa',
    'id_ed25519',
    'wp-config.php',
}
SENSITIVE_EXTENSIONS = ('.pem', '.key', '.p12', '.pfx', '.sql', '.sqlite')

GIT_READ_ONLY_TOOLS = {
    'git_list_files',
    'git_read_file',
    'git_search_code',
    'vercel_list_deployments',
}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class GitBridgeError(Exception):
    def __init__(self, message, status_code=502):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def is_git_read_only_call(tool_name):
    return tool_name in GIT_READ_ONLY_TOOLS


def sanitize_repo_path(path):
    """Normalizes a relative repo path and rejects traversal or sensitive files."""
    raw = (path or '').strip().replace('\\', '/').lstrip('/')
    if not raw:
        return ''
    parts = [p for p in raw.split('/') if p not in ('', '.')]
    if any(p == '..' for p in parts):
        raise GitBridgeError('Ruta invalida en el repositorio.', 400)
    normalized = '/'.join(parts)
    if parts and (parts[0] in ('.git', 'node_modules')):
        raise GitBridgeError('Acceso bloqueado a directorio interno.', 403)
    filename = parts[-1].lower() if parts else ''
    if (
        filename in SENSITIVE_FILENAMES
        or filename.startswith('.env.')
        or filename.endswith(SENSITIVE_EXTENSIONS)
        or 'secret' in filename
        or 'credential' in filename
    ):
        raise GitBridgeError('Acceso bloqueado a archivo sensible.', 403)
    return normalized


def _github_request(token, method, path, body=None, timeout=30):
    if not token:
        raise GitBridgeError('Falta configurar el token de GitHub para este sitio.', 400)
    url = 'https://api.github.com' + path
    data = json.dumps(body).encode('utf-8') if body is not None else None
    headers = {
        'Authorization': 'Bearer ' + token,
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'mike-control-gitops',
    }
    if data is not None:
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(req, timeout=timeout) as resp:
            raw = resp.read(524288)
        return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raise GitBridgeError(f'GitHub API HTTP {exc.code}', exc.code) from None
    except TimeoutError:
        raise GitBridgeError('Tiempo de espera agotado al conectar con GitHub.', 504) from None
    except urllib.error.URLError:
        raise GitBridgeError('No se pudo conectar con GitHub.', 502) from None
    except Exception:
        raise GitBridgeError('Error inesperado al consultar GitHub.', 500) from None


def _vercel_request(token, path, timeout=30):
    if not token:
        raise GitBridgeError('Falta configurar el token de Vercel para este sitio.', 400)
    url = 'https://api.vercel.com' + path
    req = urllib.request.Request(
        url,
        method='GET',
        headers={
            'Authorization': 'Bearer ' + token,
            'User-Agent': 'mike-control-gitops',
        },
    )
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(req, timeout=timeout) as resp:
            raw = resp.read(262144)
        return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raise GitBridgeError(f'Vercel API HTTP {exc.code}', exc.code) from None
    except TimeoutError:
        raise GitBridgeError('Tiempo de espera agotado al conectar con Vercel.', 504) from None
    except urllib.error.URLError:
        raise GitBridgeError('No se pudo conectar con Vercel.', 502) from None
    except Exception:
        raise GitBridgeError('Error inesperado al consultar Vercel.', 500) from None


def _validate_repo(repo):
    if not repo or not REPO_RE.match(repo):
        raise GitBridgeError('Repositorio GitHub invalido o sin configurar.', 400)
    return repo


def execute_git_read_tool(git_config, tool_name, args=None):
    args = args or {}
    repo = _validate_repo(git_config.get('repo', ''))
    token = git_config.get('github_token', '')
    default_branch = git_config.get('branch', 'main') or 'main'

    if tool_name == 'git_list_files':
        rel = sanitize_repo_path(args.get('path', ''))
        branch = (args.get('branch') or default_branch).strip()
        encoded_path = urllib.parse.quote(rel)
        q = urllib.parse.urlencode({'ref': branch})
        endpoint = f'/repos/{repo}/contents/{encoded_path}?{q}' if encoded_path else f'/repos/{repo}/contents?{q}'
        data = _github_request(token, 'GET', endpoint)
        if not isinstance(data, list):
            return {'path': rel, 'type': 'file', 'size': data.get('size', 0)}
        items = []
        for entry in data[:100]:
            name = entry.get('name', '')
            e_path = entry.get('path', '')
            try:
                sanitize_repo_path(e_path)
            except GitBridgeError:
                continue
            items.append({'name': name, 'path': e_path, 'type': entry.get('type'), 'size': entry.get('size', 0)})
        return {'repo': repo, 'branch': branch, 'path': rel or '/', 'entries': items}

    if tool_name == 'git_read_file':
        rel = sanitize_repo_path(args.get('path', ''))
        if not rel:
            raise GitBridgeError('Debes indicar la ruta del archivo.', 400)
        branch = (args.get('branch') or default_branch).strip()
        q = urllib.parse.urlencode({'ref': branch})
        data = _github_request(token, 'GET', f'/repos/{repo}/contents/{urllib.parse.quote(rel)}?{q}')
        if data.get('type') != 'file':
            raise GitBridgeError('La ruta indicada no es un archivo.', 400)
        if (data.get('size') or 0) > 131072:
            raise GitBridgeError('El archivo supera el limite de lectura (128 KB).', 400)
        raw_b64 = (data.get('content') or '').replace('\n', '')
        text = base64.b64decode(raw_b64).decode('utf-8', errors='replace')
        lines = text.splitlines()
        start = max(1, int(args.get('start_line') or 1))
        max_lines = min(250, max(1, int(args.get('max_lines') or 200)))
        slice_lines = lines[start - 1 : start - 1 + max_lines]
        return {
            'repo': repo,
            'branch': branch,
            'path': rel,
            'sha': data.get('sha'),
            'total_lines': len(lines),
            'start_line': start,
            'content': '\n'.join(slice_lines),
        }

    if tool_name == 'git_search_code':
        query = (args.get('query') or '').strip()
        if not query or len(query) > 120:
            raise GitBridgeError('Consulta de busqueda invalida.', 400)
        q = urllib.parse.urlencode({'q': f'{query} repo:{repo}', 'per_page': 20})
        data = _github_request(token, 'GET', f'/search/code?{q}')
        matches = []
        for item in (data.get('items') or [])[:20]:
            p = item.get('path', '')
            try:
                sanitize_repo_path(p)
            except GitBridgeError:
                continue
            matches.append({'path': p, 'name': item.get('name')})
        return {'repo': repo, 'query': query, 'total_count': data.get('total_count', 0), 'items': matches}

    if tool_name == 'vercel_list_deployments':
        v_token = git_config.get('vercel_token', '')
        v_proj = git_config.get('vercel_project_id', '')
        if not v_token or not v_proj:
            return {'configured': False, 'message': 'Vercel API no configurada para este sitio; las URLs de Preview se ven en el Pull Request de GitHub.'}
        limit = min(10, max(1, int(args.get('limit') or 5)))
        q = urllib.parse.urlencode({'projectId': v_proj, 'limit': limit})
        data = _vercel_request(v_token, f'/v6/deployments?{q}')
        deps = [
            {
                'uid': d.get('uid'),
                'url': 'https://' + d['url'] if d.get('url') else None,
                'state': d.get('readyState') or d.get('state'),
                'target': d.get('target') or 'preview',
                'created': d.get('created'),
            }
            for d in (data.get('deployments') or [])[:limit]
        ]
        return {'configured': True, 'deployments': deps}

    raise GitBridgeError(f'Herramienta Git desconocida: {tool_name}', 400)


def execute_git_proposal(git_config, proposal_id, tool_name, args=None):
    """Executes an approved write proposal against GitHub (feature branch + PR or PR merge)."""
    args = args or {}
    repo = _validate_repo(git_config.get('repo', ''))
    token = git_config.get('github_token', '')
    base_branch = git_config.get('branch', 'main') or 'main'

    if tool_name == 'git_propose_file_change':
        rel = sanitize_repo_path(args.get('path', ''))
        if not rel:
            raise GitBridgeError('Ruta de archivo requerida.', 400)
        content = args.get('content')
        if not isinstance(content, str):
            raise GitBridgeError('Contenido de archivo invalido.', 400)
        commit_message = (args.get('commit_message') or f'mike-control: update {rel}').strip()[:120]
        pr_title = (args.get('pr_title') or commit_message).strip()[:120]
        pr_body = (args.get('pr_body') or f'Propuesta #{proposal_id} aprobada en mike-control.').strip()[:2000]

        # 1. Get base branch SHA
        ref = _github_request(token, 'GET', f'/repos/{repo}/git/ref/heads/{urllib.parse.quote(base_branch)}')
        base_sha = (ref.get('object') or {}).get('sha')
        if not base_sha:
            raise GitBridgeError('No se pudo obtener el commit base de la rama principal.', 502)

        # 2. Create isolated feature branch
        feature_branch = f'mike/prop-{proposal_id}'
        _github_request(
            token,
            'POST',
            f'/repos/{repo}/git/refs',
            body={'ref': f'refs/heads/{feature_branch}', 'sha': base_sha},
        )

        # 3. Check existing file SHA on feature branch (if updating)
        existing_sha = None
        try:
            q = urllib.parse.urlencode({'ref': feature_branch})
            existing = _github_request(token, 'GET', f'/repos/{repo}/contents/{urllib.parse.quote(rel)}?{q}')
            existing_sha = existing.get('sha')
        except GitBridgeError as exc:
            if exc.status_code != 404:
                raise

        put_body = {
            'message': commit_message,
            'content': base64.b64encode(content.encode('utf-8')).decode('ascii'),
            'branch': feature_branch,
        }
        if existing_sha:
            put_body['sha'] = existing_sha

        commit_res = _github_request(
            token,
            'PUT',
            f'/repos/{repo}/contents/{urllib.parse.quote(rel)}',
            body=put_body,
        )

        # 4. Open Pull Request (triggers Vercel Preview automatically)
        pr_res = _github_request(
            token,
            'POST',
            f'/repos/{repo}/pulls',
            body={
                'title': pr_title,
                'head': feature_branch,
                'base': base_branch,
                'body': pr_body,
            },
        )
        return {
            'repo': repo,
            'branch': feature_branch,
            'commit_sha': ((commit_res.get('commit') or {}).get('sha')),
            'pr_number': pr_res.get('number'),
            'pr_url': pr_res.get('html_url'),
        }

    if tool_name == 'git_propose_merge_pr':
        pr_number = int(args.get('pr_number') or 0)
        if pr_number <= 0:
            raise GitBridgeError('Numero de Pull Request invalido.', 400)
        commit_title = (args.get('commit_title') or f'Merge PR #{pr_number} (aprobado en mike-control)').strip()[:120]
        merge_res = _github_request(
            token,
            'PUT',
            f'/repos/{repo}/pulls/{pr_number}/merge',
            body={'commit_title': commit_title, 'merge_method': 'squash'},
        )
        return {
            'repo': repo,
            'pr_number': pr_number,
            'merged': bool(merge_res.get('merged')),
            'sha': merge_res.get('sha'),
            'message': merge_res.get('message'),
        }

    raise GitBridgeError(f'Propuesta Git desconocida: {tool_name}', 400)


GIT_TOOLS_SCHEMA = [
    {
        'type': 'function',
        'name': 'git_list_files',
        'description': 'Lista archivos y carpetas del repositorio GitHub del sitio (Astro/Node/React). Solo lectura.',
        'parameters': {
            'type': 'object',
            'properties': {
                'path': {'type': 'string', 'description': 'Subcarpeta relativa (vacio para la raiz).'},
                'branch': {'type': 'string', 'description': 'Rama opcional (por defecto la principal).'},
            },
            'required': [],
        },
    },
    {
        'type': 'function',
        'name': 'git_read_file',
        'description': 'Lee el contenido de un archivo del repositorio GitHub (bloquea .env y llaves). Solo lectura.',
        'parameters': {
            'type': 'object',
            'properties': {
                'path': {'type': 'string', 'description': 'Ruta relativa del archivo, ej: src/pages/index.astro'},
                'start_line': {'type': 'integer', 'description': 'Linea inicial (1 por defecto).'},
                'max_lines': {'type': 'integer', 'description': 'Cantidad maxima de lineas (hasta 250).'},
                'branch': {'type': 'string', 'description': 'Rama opcional.'},
            },
            'required': ['path'],
        },
    },
    {
        'type': 'function',
        'name': 'git_search_code',
        'description': 'Busca texto o simbolos en el repositorio GitHub del sitio. Solo lectura.',
        'parameters': {
            'type': 'object',
            'properties': {
                'query': {'type': 'string', 'description': 'Texto a buscar en el codigo.'},
            },
            'required': ['query'],
        },
    },
    {
        'type': 'function',
        'name': 'vercel_list_deployments',
        'description': 'Consulta los ultimos deployments de Vercel (URLs de Preview y estado) si esta configurado. Solo lectura.',
        'parameters': {
            'type': 'object',
            'properties': {
                'limit': {'type': 'integer', 'description': 'Cantidad de deployments (1 a 10).'},
            },
            'required': [],
        },
    },
    {
        'type': 'function',
        'name': 'git_propose_file_change',
        'description': 'Crea una propuesta para modificar o crear un archivo en una rama nueva y abrir un Pull Request en GitHub (dispara Vercel Preview). Requiere aprobacion del propietario.',
        'parameters': {
            'type': 'object',
            'properties': {
                'path': {'type': 'string', 'description': 'Ruta relativa del archivo a crear o actualizar.'},
                'content': {'type': 'string', 'description': 'Contenido completo nuevo del archivo.'},
                'commit_message': {'type': 'string', 'description': 'Mensaje corto del commit.'},
                'pr_title': {'type': 'string', 'description': 'Titulo del Pull Request.'},
                'pr_body': {'type': 'string', 'description': 'Descripcion del cambio para revision.'},
            },
            'required': ['path', 'content', 'commit_message', 'pr_title'],
        },
    },
    {
        'type': 'function',
        'name': 'git_propose_merge_pr',
        'description': 'Crea una propuesta para hacer merge de un Pull Request ya revisado hacia produccion (main). Requiere aprobacion del propietario.',
        'parameters': {
            'type': 'object',
            'properties': {
                'pr_number': {'type': 'integer', 'description': 'Numero del Pull Request en GitHub.'},
                'commit_title': {'type': 'string', 'description': 'Titulo del merge commit.'},
            },
            'required': ['pr_number'],
        },
    },
]
