"""First backend milestone: protected dashboard and durable conversation archive.
Optional conversational AI; no SSH, scheduler or execution tools.
"""
import json
import logging
import os
import secrets
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from threading import Lock
from threading import Event, Thread
from backend.monitor import probe, INTERVAL_SECONDS
from backend.ai import Responder, AIUnavailable
from backend.wp_bridge import BridgeError, execute_remote_tool, params_hash as compute_params_hash
from backend.git_bridge import GitBridgeError, execute_git_proposal
from pathlib import Path
from typing import Annotated

import psycopg
from psycopg.rows import dict_row
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
AGENTS = ('mike', 'usbestroofing', 'centrotai', 'pacific', 'gabriels')
WP_AGENT_ENV_PREFIXES = {'centrotai': 'CENTROTAI', 'usbestroofing': 'USBESTROOFING'}
GIT_AGENT_ENV_PREFIXES = {'pacific': 'PACIFIC', 'gabriels': 'GABRIELS'}
SITE_DISPLAY_NAMES = {
    'centrotai': 'Centro TAI',
    'usbestroofing': 'US Best Roofing',
    'pacific': 'Pacific',
    'gabriels': 'Gabriels',
}

@dataclass(frozen=True)
class Settings:
    database_url: str
    username: str
    password: str = field(repr=False)
    api_key: str = field(default="", repr=False)
    model: str = "gpt-5-mini"
    monitor_enabled: bool = False
    wp_sites: dict = field(default_factory=dict, repr=False)
    ssh_sites: dict = field(default_factory=dict, repr=False)
    git_sites: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_env(cls):
        values = [os.environ.get(k, '') for k in ('DATABASE_URL', 'ADMIN_USERNAME', 'ADMIN_PASSWORD')]
        if not all(values) or len(values[2]) < 24:
            raise RuntimeError('Set DATABASE_URL, ADMIN_USERNAME and ADMIN_PASSWORD (24+ characters).')
        wp_sites = {}
        ssh_sites = {}
        for site_id, prefix in WP_AGENT_ENV_PREFIXES.items():
            url = os.environ.get(f'{prefix}_WP_URL', '').strip().rstrip('/')
            secret = os.environ.get(f'{prefix}_WP_BRIDGE_SECRET', '').strip()
            if url and secret:
                wp_sites[site_id] = {'url': url, 'bridge_secret': secret, 'name': SITE_DISPLAY_NAMES.get(site_id, site_id)}
            ssh_host = os.environ.get(f'{prefix}_SSH_HOST', '').strip()
            ssh_user = os.environ.get(f'{prefix}_SSH_USER', '').strip()
            ssh_key = os.environ.get(f'{prefix}_SSH_KEY', '').strip()
            ssh_host_key = os.environ.get(f'{prefix}_SSH_HOST_KEY', '').strip()
            ssh_root = os.environ.get(f'{prefix}_SSH_ROOT', '/var/www/html').strip()
            if ssh_host and ssh_user and ssh_key and ssh_host_key:
                ssh_sites[site_id] = {
                    'host': ssh_host,
                    'port': int(os.environ.get(f'{prefix}_SSH_PORT', '22') or '22'),
                    'username': ssh_user,
                    'private_key': ssh_key,
                    'host_key': ssh_host_key,
                    'root_path': ssh_root,
                    'name': SITE_DISPLAY_NAMES.get(site_id, site_id),
                }
        git_sites = {}
        for site_id, prefix in GIT_AGENT_ENV_PREFIXES.items():
            repo = os.environ.get(f'{prefix}_GITHUB_REPO', '').strip()
            gh_token = os.environ.get(f'{prefix}_GITHUB_TOKEN', '').strip()
            if repo and gh_token:
                git_sites[site_id] = {
                    'repo': repo,
                    'github_token': gh_token,
                    'branch': os.environ.get(f'{prefix}_GITHUB_BRANCH', 'main').strip() or 'main',
                    'vercel_token': os.environ.get(f'{prefix}_VERCEL_TOKEN', '').strip(),
                    'vercel_project_id': os.environ.get(f'{prefix}_VERCEL_PROJECT_ID', '').strip(),
                    'name': SITE_DISPLAY_NAMES.get(site_id, site_id),
                }
        return cls(*values, api_key=os.environ.get("OPENAI_API_KEY", "").strip(),
                   model=os.environ.get("OPENAI_MODEL", "gpt-5-mini").strip(),
                   monitor_enabled=os.environ.get('MONITOR_ENABLED', '').lower() == 'true',
                   wp_sites=wp_sites,
                   ssh_sites=ssh_sites,
                   git_sites=git_sites)

class Store:
    def __init__(self, url):
        self.url = url

    def connect(self):
        return psycopg.connect(self.url, connect_timeout=5, row_factory=dict_row,
                               options='-c statement_timeout=10000')

    def initialize(self):
        with self.connect() as conn:
            # Serializes initialization when two instances start simultaneously.
            conn.execute('SELECT pg_advisory_xact_lock(87319451)')
            conn.execute('''CREATE TABLE IF NOT EXISTS conversation_messages (
                id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                agent_id text NOT NULL CHECK(agent_id IN ('mike','usbestroofing')),
                role text NOT NULL CHECK(role IN ('user','system')),
                content text NOT NULL CHECK(length(content) BETWEEN 1 AND 8000),
                created_at timestamptz NOT NULL DEFAULT now()
            )''')
            # Upgrade the original constraints transactionally without deleting history.
            conn.execute('ALTER TABLE conversation_messages DROP CONSTRAINT IF EXISTS conversation_messages_agent_id_check')
            conn.execute("ALTER TABLE conversation_messages ADD CONSTRAINT conversation_messages_agent_id_check CHECK(agent_id IN ('mike','usbestroofing','centrotai','pacific','gabriels'))")
            conn.execute('ALTER TABLE conversation_messages DROP CONSTRAINT IF EXISTS conversation_messages_role_check')
            conn.execute("ALTER TABLE conversation_messages ADD CONSTRAINT conversation_messages_role_check CHECK(role IN ('user','system','assistant'))")
            conn.execute('''CREATE INDEX IF NOT EXISTS messages_agent_id_idx
                ON conversation_messages(agent_id, id DESC)''')
            conn.execute('''CREATE TABLE IF NOT EXISTS availability_checks (
                id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                site_id text NOT NULL, checked_at timestamptz NOT NULL DEFAULT now(),
                status text NOT NULL, http_status integer, duration_ms integer NOT NULL)''')
            conn.execute('''CREATE TABLE IF NOT EXISTS proposals (
                id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                site_id text NOT NULL CHECK(site_id IN ('usbestroofing','centrotai','pacific','gabriels')),
                tool_name text NOT NULL,
                params_json jsonb NOT NULL DEFAULT '{}'::jsonb,
                params_hash text NOT NULL,
                status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','executing','executed','failed','rejected','expired')),
                expires_at timestamptz NOT NULL,
                created_at timestamptz NOT NULL DEFAULT now(),
                executed_at timestamptz,
                result_json jsonb)''')
            conn.execute('''CREATE INDEX IF NOT EXISTS proposals_status_idx
                ON proposals(status, id DESC)''')
            conn.execute('ALTER TABLE proposals DROP CONSTRAINT IF EXISTS proposals_site_id_check')
            conn.execute("ALTER TABLE proposals ADD CONSTRAINT proposals_site_id_check CHECK(site_id IN ('usbestroofing','centrotai','pacific','gabriels'))")

    def check_if_due(self):
        # Transaction lock makes the decision and check exclusive across workers.
        with self.connect() as conn:
            if not conn.execute('SELECT pg_try_advisory_xact_lock(87319452) AS locked').fetchone()['locked']:
                return
            due = conn.execute("""SELECT NOT EXISTS (SELECT 1 FROM availability_checks
                WHERE site_id='usbestroofing' AND checked_at > now() - interval '15 minutes') AS due""").fetchone()['due']
            if due:
                result = probe()
                conn.execute('INSERT INTO availability_checks(site_id,status,http_status,duration_ms) VALUES (%s,%s,%s,%s)',
                             ('usbestroofing', result['status'], result['http_status'], result['duration_ms']))

    def latest_check(self):
        with self.connect() as conn:
            return conn.execute("""SELECT checked_at,status,http_status,duration_ms FROM availability_checks
                WHERE site_id='usbestroofing' ORDER BY id DESC LIMIT 1""").fetchone()

    def ready(self):
        with self.connect() as conn:
            conn.execute('SELECT 1').fetchone()

    def messages(self, agent):
        with self.connect() as conn:
            rows = conn.execute('''SELECT id, role, content, created_at FROM
                conversation_messages WHERE agent_id=%s ORDER BY id DESC LIMIT 100''',
                (agent,)).fetchall()
        return list(reversed(rows))

    def append(self, agent, text, role="user"):
        with self.connect() as conn:
            return conn.execute('''INSERT INTO conversation_messages(agent_id,role,content)
                VALUES (%s,%s,%s) RETURNING id,role,content,created_at''',
                (agent,role,text)).fetchone()

    def create_proposal(self, site_id, tool_name, args, ttl_minutes=15):
        params = args or {}
        p_hash = compute_params_hash(tool_name, params)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)
        with self.connect() as conn:
            return conn.execute('''INSERT INTO proposals(site_id,tool_name,params_json,params_hash,status,expires_at)
                VALUES (%s,%s,%s::jsonb,%s,'pending',%s)
                RETURNING id,site_id,tool_name,params_json,params_hash,status,expires_at,created_at''',
                (site_id, tool_name, json.dumps(params, sort_keys=True), p_hash, expires_at)).fetchone()

    def list_proposals(self, site_id=None, limit=50):
        with self.connect() as conn:
            conn.execute("UPDATE proposals SET status='expired' WHERE status='pending' AND expires_at <= now()")
            if site_id:
                return conn.execute('''SELECT id,site_id,tool_name,params_json,params_hash,status,expires_at,created_at,executed_at,result_json
                    FROM proposals WHERE site_id=%s ORDER BY id DESC LIMIT %s''', (site_id, limit)).fetchall()
            return conn.execute('''SELECT id,site_id,tool_name,params_json,params_hash,status,expires_at,created_at,executed_at,result_json
                FROM proposals ORDER BY id DESC LIMIT %s''', (limit,)).fetchall()

    def get_proposal(self, proposal_id):
        with self.connect() as conn:
            return conn.execute('''SELECT id,site_id,tool_name,params_json,params_hash,status,expires_at,created_at,executed_at,result_json
                FROM proposals WHERE id=%s''', (proposal_id,)).fetchone()

    def consume_proposal(self, proposal_id):
        with self.connect() as conn:
            return conn.execute('''UPDATE proposals SET status='executing'
                WHERE id=%s AND status='pending' AND expires_at > now()
                RETURNING id,site_id,tool_name,params_json,params_hash,status,expires_at,created_at''',
                (proposal_id,)).fetchone()

    def finish_proposal(self, proposal_id, status, result):
        with self.connect() as conn:
            return conn.execute('''UPDATE proposals SET status=%s, executed_at=now(), result_json=%s::jsonb
                WHERE id=%s
                RETURNING id,site_id,tool_name,params_json,params_hash,status,expires_at,created_at,executed_at,result_json''',
                (status, json.dumps(result or {}), proposal_id)).fetchone()

    def reject_proposal(self, proposal_id):
        with self.connect() as conn:
            return conn.execute('''UPDATE proposals SET status='rejected'
                WHERE id=%s AND status='pending'
                RETURNING id,site_id,tool_name,params_json,params_hash,status,expires_at,created_at''',
                (proposal_id,)).fetchone()

class Message(BaseModel):
    content: str = Field(min_length=1, max_length=8000)


def create_app(settings=None, store=None, responder=None):
    settings = settings or Settings.from_env()
    store = store or Store(settings.database_url)
    security = HTTPBasic()
    responder = responder or (Responder(settings.api_key, settings.model) if settings.api_key else None)
    # Docker runs one worker. Reject simultaneous sends instead of interleaving turns.
    chat_locks = {agent: Lock() for agent in AGENTS}

    @asynccontextmanager
    async def lifespan(app):
        store.initialize()
        stop = Event()
        worker = None
        if settings.monitor_enabled:
            def run():
                while not stop.is_set():
                    try:
                        store.check_if_due()
                    except Exception:
                        logging.getLogger('mike.monitor').warning('Monitor check failed; will retry')
                    stop.wait(60)
            worker = Thread(target=run, daemon=True, name='availability-monitor')
            worker.start()
        try:
            yield
        finally:
            stop.set()
            if worker:
                worker.join(timeout=12)

    app = FastAPI(title='Mike Control', lifespan=lifespan, docs_url=None,
                  redoc_url=None, openapi_url=None)

    def owner(credentials: Annotated[HTTPBasicCredentials, Depends(security)]):
        valid_user = secrets.compare_digest(credentials.username.encode(), settings.username.encode())
        valid_pass = secrets.compare_digest(credentials.password.encode(), settings.password.encode())
        if not (valid_user and valid_pass):
            raise HTTPException(401, 'Authentication required', headers={'WWW-Authenticate':'Basic realm="Mike"'})

    @app.middleware('http')
    async def headers_and_size(request: Request, call_next):
        # Browser cross-site writes are forbidden; frontend uses this custom header.
        if request.method not in ('GET','HEAD','OPTIONS'):
            if request.headers.get('x-mike-request') != '1' or request.headers.get('sec-fetch-site') == 'cross-site':
                return JSONResponse({'detail':'Request rejected'},status_code=403)
        if request.method == 'POST':
            # Read with a hard cap, including chunked bodies. Do not trust Content-Length.
            size=0
            chunks=[]
            async for chunk in request.stream():
                size += len(chunk)
                chunks.append(chunk)
                if size > 40000:
                    return JSONResponse({'detail':'Body too large'},status_code=413)
            request._body = b"".join(chunks)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Content-Security-Policy'] = "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        return response

    @app.exception_handler(psycopg.Error)
    async def unavailable(request, exc):
        # Never return connection strings or database exception text to the browser.
        return JSONResponse({'detail':'Database temporarily unavailable'}, status_code=503)

    @app.get('/health/live')
    def live():
        return {'status':'alive'}

    @app.get('/health/ready', dependencies=[Depends(owner)])
    def ready():
        store.ready()
        return {'status':'ready'}

    @app.get('/', dependencies=[Depends(owner)])
    def index():
        return FileResponse(ROOT/'web'/'app.html')

    @app.get('/app.js', dependencies=[Depends(owner)])
    def script():
        return FileResponse(ROOT/'web'/'app.js', media_type='text/javascript')

    @app.get('/api/status', dependencies=[Depends(owner)])
    def status():
        store.ready()
        has_execution = bool(settings.wp_sites or settings.git_sites)
        return {'database':'connected', 'ai':'configured' if responder else 'not_connected', 'telegram':'not_connected',
                'ssh':'read_only' if settings.ssh_sites else 'not_connected',
                'monitoring':'enabled' if settings.monitor_enabled else 'disabled', 'scan_interval_minutes':15,
                'latest_check':store.latest_check(),
                'execution':'approval_required' if has_execution else 'disabled',
                'wp_sites':sorted(settings.wp_sites.keys()),
                'ssh_sites':sorted(settings.ssh_sites.keys()),
                'git_sites':sorted(settings.git_sites.keys()),
                'agents':[{'id':'mike','name':'Mike'},
                    {'id':'usbestroofing','name':'US Best Roofing'},
                    {'id':'centrotai','name':'Centro TAI'},
                    {'id':'pacific','name':'Pacific'},
                    {'id':'gabriels','name':'Gabriels'}]}

    def check_agent(agent):
        if agent not in AGENTS:
            raise HTTPException(404, 'Unknown agent')

    @app.get('/api/agents/{agent}/messages', dependencies=[Depends(owner)])
    def messages(agent: str):
        check_agent(agent)
        return {'messages':store.messages(agent)}

    @app.post('/api/agents/{agent}/messages', dependencies=[Depends(owner)], status_code=201)
    def append(agent: str, body: Message):
        check_agent(agent)
        text = body.content.strip()
        if not text:
            raise HTTPException(422, 'Message cannot be blank')
        lock = chat_locks[agent]
        if not lock.acquire(blocking=False):
            raise HTTPException(409, 'This chat already has a response in progress')
        try:
            message = store.append(agent,text)
            result = {'message':message, 'ai':'not_connected'}
            if responder is not None:
                try:
                    if isinstance(responder, Responder):
                        answer = responder.reply(
                            agent,
                            store.messages(agent),
                            site_config=settings.wp_sites.get(agent),
                            proposal_creator=getattr(store, 'create_proposal', None),
                            ssh_config=settings.ssh_sites.get(agent),
                            git_config=settings.git_sites.get(agent),
                        )
                    else:
                        answer = responder.reply(agent, store.messages(agent))
                    result['reply'] = store.append(agent,answer,role='assistant')
                    result['ai'] = 'responded'
                except AIUnavailable as exc:
                    # User message is already durable. Never expose provider bodies or keys.
                    logging.getLogger('mike.ai').warning('AI response failed: %s', exc.reason)
                    result.update(ai='unavailable', ai_error=exc.reason,
                                  warning='Mensaje guardado. ' + exc.user_message + ' [Diagnóstico: ' + exc.reason + ']')
            return result
        finally:
            lock.release()

    @app.get('/api/proposals', dependencies=[Depends(owner)])
    def list_proposals(site_id: str | None = None):
        if site_id is not None:
            check_agent(site_id)
        return {'proposals': store.list_proposals(site_id=site_id)}

    @app.post('/api/proposals/{proposal_id}/approve', dependencies=[Depends(owner)])
    def approve_proposal(proposal_id: int):
        existing = store.get_proposal(proposal_id)
        if not existing:
            raise HTTPException(404, 'Proposal not found')
        is_git = existing['tool_name'].startswith('git_')
        if is_git:
            git_config = settings.git_sites.get(existing['site_id'])
            if not git_config:
                raise HTTPException(400, 'GitHub/Vercel bridge not configured for this site')
        else:
            site_config = settings.wp_sites.get(existing['site_id'])
            if not site_config:
                raise HTTPException(400, 'WordPress bridge not configured for this site')
        proposal = store.consume_proposal(proposal_id)
        if not proposal:
            raise HTTPException(409, 'Proposal is no longer pending or has expired')
        params = proposal.get('params_json') or {}
        if compute_params_hash(proposal['tool_name'], params) != proposal['params_hash']:
            store.finish_proposal(proposal_id, 'failed', {'error': 'Proposal integrity check failed'})
            raise HTTPException(409, 'Proposal integrity check failed')
        try:
            if is_git:
                result = execute_git_proposal(git_config, proposal_id, proposal['tool_name'], params)
            else:
                result = execute_remote_tool(site_config['url'], site_config['bridge_secret'], proposal['tool_name'], params)
        except (BridgeError, GitBridgeError) as exc:
            store.finish_proposal(proposal_id, 'failed', {'error': str(exc)})
            raise HTTPException(502, str(exc))
        updated = store.finish_proposal(proposal_id, 'executed', result)
        return {'proposal': updated, 'result': result}

    @app.post('/api/proposals/{proposal_id}/reject', dependencies=[Depends(owner)])
    def reject_proposal(proposal_id: int):
        existing = store.get_proposal(proposal_id)
        if not existing:
            raise HTTPException(404, 'Proposal not found')
        updated = store.reject_proposal(proposal_id)
        if not updated:
            raise HTTPException(409, 'Proposal is no longer pending')
        return {'proposal': updated}

    return app
