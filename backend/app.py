"""First backend milestone: protected dashboard and durable conversation archive.
Optional conversational AI; no SSH, scheduler or execution tools.
"""
import json
import logging
import os
import re
import secrets
import time
import traceback
from collections import defaultdict
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from threading import Lock
from threading import Event, Thread
from backend.monitor import probe, validate_public_http_url, INTERVAL_SECONDS, URL as DEFAULT_MONITOR_URL
from backend.ai import Responder, AIUnavailable
from backend.daily_reports import REPORT_HOUR, REPORT_TIMEZONE, run_daily_report
from backend.wp_bridge import BridgeError, execute_remote_tool, params_hash as compute_params_hash
from backend.git_bridge import GitBridgeError, execute_git_proposal
from pathlib import Path
from typing import Annotated

import psycopg
from psycopg.rows import dict_row
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.encoders import jsonable_encoder
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
SITE_ID_RE = re.compile(r'^[a-z0-9][a-z0-9_-]{1,31}$')
DEFAULT_SITES = (
    {'id': 'usbestroofing', 'name': 'US Best Roofing', 'kind': 'wordpress'},
    {'id': 'centrotai', 'name': 'Centro TAI', 'kind': 'wordpress'},
    {'id': 'pacific', 'name': 'Pacific', 'kind': 'vercel'},
    {'id': 'gabriels', 'name': 'Gabriels', 'kind': 'vercel'},
)
SITE_DISPLAY_NAMES = {s['id']: s['name'] for s in DEFAULT_SITES}

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
    daily_reports_enabled: bool = False

    @classmethod
    def from_env(cls):
        values = [os.environ.get(k, '') for k in ('DATABASE_URL', 'ADMIN_USERNAME', 'ADMIN_PASSWORD')]
        if not all(values) or len(values[2]) < 24:
            raise RuntimeError('Set DATABASE_URL, ADMIN_USERNAME and ADMIN_PASSWORD (24+ characters).')

        def display_name(site_id, prefix):
            custom = os.environ.get(f'{prefix}_SITE_NAME', '').strip()
            return custom or SITE_DISPLAY_NAMES.get(site_id, prefix.replace('_', ' ').title())

        wp_sites = {}
        for key in list(os.environ.keys()):
            if key.endswith('_WP_URL'):
                prefix = key[:-len('_WP_URL')]
                site_id = prefix.lower()
                if not prefix or site_id == 'mike' or not SITE_ID_RE.match(site_id):
                    continue
                url = os.environ.get(key, '').strip().rstrip('/')
                secret = os.environ.get(f'{prefix}_WP_BRIDGE_SECRET', '').strip()
                if url and secret:
                    wp_sites[site_id] = {'url': url, 'bridge_secret': secret, 'name': display_name(site_id, prefix)}

        ssh_sites = {}
        for key in list(os.environ.keys()):
            if key.endswith('_SSH_HOST'):
                prefix = key[:-len('_SSH_HOST')]
                site_id = prefix.lower()
                if not prefix or site_id == 'mike' or not SITE_ID_RE.match(site_id):
                    continue
                ssh_host = os.environ.get(key, '').strip()
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
                        'name': display_name(site_id, prefix),
                    }

        git_sites = {}
        for key in list(os.environ.keys()):
            if key.endswith('_GITHUB_REPO'):
                prefix = key[:-len('_GITHUB_REPO')]
                site_id = prefix.lower()
                if not prefix or site_id == 'mike' or not SITE_ID_RE.match(site_id):
                    continue
                repo = os.environ.get(key, '').strip()
                gh_token = os.environ.get(f'{prefix}_GITHUB_TOKEN', '').strip()
                if repo and gh_token:
                    git_sites[site_id] = {
                        'repo': repo,
                        'github_token': gh_token,
                        'branch': os.environ.get(f'{prefix}_GITHUB_BRANCH', 'main').strip() or 'main',
                        'vercel_token': os.environ.get(f'{prefix}_VERCEL_TOKEN', '').strip(),
                        'vercel_project_id': os.environ.get(f'{prefix}_VERCEL_PROJECT_ID', '').strip(),
                        'site_url': os.environ.get(f'{prefix}_SITE_URL', '').strip(),
                        'name': display_name(site_id, prefix),
                    }

        return cls(*values, api_key=os.environ.get("OPENAI_API_KEY", "").strip(),
                   model=os.environ.get("OPENAI_MODEL", "gpt-5-mini").strip(),
                   monitor_enabled=os.environ.get('MONITOR_ENABLED', '').lower() == 'true',
                   wp_sites=wp_sites,
                   ssh_sites=ssh_sites,
                   git_sites=git_sites,
                   daily_reports_enabled=os.environ.get('DAILY_REPORTS_ENABLED', 'true').lower() == 'true')

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
            conn.execute('''CREATE TABLE IF NOT EXISTS sites (
                id text PRIMARY KEY CHECK(id ~ '^[a-z0-9][a-z0-9_-]{1,31}$' AND id <> 'mike'),
                name text NOT NULL CHECK(length(name) BETWEEN 1 AND 80),
                kind text NOT NULL CHECK(kind IN ('wordpress','vercel')),
                url text,
                hidden boolean NOT NULL DEFAULT false,
                created_at timestamptz NOT NULL DEFAULT now()
            )''')
            conn.execute('ALTER TABLE sites ADD COLUMN IF NOT EXISTS url text')
            conn.execute('ALTER TABLE sites ADD COLUMN IF NOT EXISTS hidden boolean NOT NULL DEFAULT false')
            conn.execute('''CREATE TABLE IF NOT EXISTS conversation_messages (
                id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                agent_id text NOT NULL,
                role text NOT NULL CHECK(role IN ('user','system')),
                content text NOT NULL CHECK(length(content) BETWEEN 1 AND 8000),
                created_at timestamptz NOT NULL DEFAULT now()
            )''')
            # Upgrade the original constraints transactionally without deleting history.
            conn.execute('ALTER TABLE conversation_messages DROP CONSTRAINT IF EXISTS conversation_messages_agent_id_check')
            conn.execute("ALTER TABLE conversation_messages ADD CONSTRAINT conversation_messages_agent_id_check CHECK(agent_id ~ '^[a-z0-9][a-z0-9_-]{1,31}$')")
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
                site_id text NOT NULL,
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
            conn.execute("ALTER TABLE proposals ADD CONSTRAINT proposals_site_id_check CHECK(site_id ~ '^[a-z0-9][a-z0-9_-]{1,31}$')")
            conn.execute('''CREATE TABLE IF NOT EXISTS daily_reports (
                report_date date PRIMARY KEY,
                status text NOT NULL CHECK(status IN ('running','completed','partial','failed')),
                started_at timestamptz NOT NULL DEFAULT now(),
                finished_at timestamptz,
                summary_json jsonb NOT NULL DEFAULT '{}'::jsonb
            )''')

    def claim_daily_report(self, report_date):
        with self.connect() as conn:
            # A restart must never repeat a date that may already have incurred API usage.
            conn.execute("""UPDATE daily_reports SET status='failed', finished_at=now(),
                summary_json='{"error":"interrupted"}'::jsonb
                WHERE status='running' AND report_date < %s""", (report_date,))
            row = conn.execute("""INSERT INTO daily_reports(report_date,status)
                VALUES (%s,'running') ON CONFLICT DO NOTHING RETURNING report_date""",
                (report_date,)).fetchone()
            return row is not None

    def finish_daily_report(self, report_date, status, parts, summary):
        with self.connect() as conn:
            row = conn.execute("""SELECT status FROM daily_reports
                WHERE report_date=%s FOR UPDATE""", (report_date,)).fetchone()
            if not row or row['status'] != 'running':
                return
            for part in parts:
                conn.execute("""INSERT INTO conversation_messages(agent_id,role,content)
                    VALUES ('mike','assistant',%s)""", (part,))
            conn.execute("""UPDATE daily_reports SET status=%s, finished_at=now(), summary_json=%s::jsonb
                WHERE report_date=%s""", (status, json.dumps(summary), report_date))

    def latest_daily_report(self):
        with self.connect() as conn:
            return conn.execute('SELECT * FROM daily_reports ORDER BY report_date DESC LIMIT 1').fetchone()

    def check_if_due(self, targets=None):
        # Transaction lock makes the decision and check exclusive across workers.
        targets = targets if targets is not None else [('usbestroofing', DEFAULT_MONITOR_URL)]
        with self.connect() as conn:
            if not conn.execute('SELECT pg_try_advisory_xact_lock(87319452) AS locked').fetchone()['locked']:
                return
            for site_id, target_url in targets:
                if not target_url:
                    continue
                due = conn.execute("""SELECT NOT EXISTS (SELECT 1 FROM availability_checks
                    WHERE site_id=%s AND checked_at > now() - interval '15 minutes') AS due""", (site_id,)).fetchone()['due']
                if due:
                    try:
                        result = probe(url=target_url)
                    except TypeError:
                        result = probe()
                    conn.execute('INSERT INTO availability_checks(site_id,status,http_status,duration_ms) VALUES (%s,%s,%s,%s)',
                                 (site_id, result['status'], result['http_status'], result['duration_ms']))

    def record_check(self, site_id, target_url):
        try:
            result = probe(url=target_url)
        except TypeError:
            result = probe()
        with self.connect() as conn:
            return conn.execute('''INSERT INTO availability_checks(site_id,status,http_status,duration_ms)
                VALUES (%s,%s,%s,%s) RETURNING site_id,checked_at,status,http_status,duration_ms''',
                (site_id, result['status'], result['http_status'], result['duration_ms'])).fetchone()

    def latest_check(self):
        with self.connect() as conn:
            return conn.execute("""SELECT checked_at,status,http_status,duration_ms FROM availability_checks
                WHERE site_id='usbestroofing' ORDER BY id DESC LIMIT 1""").fetchone()

    def latest_checks_by_site(self):
        with self.connect() as conn:
            return conn.execute('''SELECT DISTINCT ON (site_id) site_id,checked_at,status,http_status,duration_ms
                FROM availability_checks ORDER BY site_id, id DESC''').fetchall()

    def recent_incidents(self, limit=25):
        with self.connect() as conn:
            return conn.execute("""SELECT site_id,checked_at,status,http_status,duration_ms
                FROM availability_checks WHERE status <> 'ok' ORDER BY id DESC LIMIT %s""", (limit,)).fetchall()

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

    def list_sites(self):
        with self.connect() as conn:
            return conn.execute('SELECT id,name,kind,url,hidden,created_at FROM sites ORDER BY created_at ASC, id ASC').fetchall()

    def upsert_site(self, site_id, name, kind, url=None):
        clean_url = (url or '').strip() or None
        with self.connect() as conn:
            return conn.execute('''INSERT INTO sites(id,name,kind,url,hidden) VALUES (%s,%s,%s,%s,false)
                ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name, kind=EXCLUDED.kind, url=COALESCE(EXCLUDED.url, sites.url), hidden=false
                RETURNING id,name,kind,url,created_at''', (site_id, name, kind, clean_url)).fetchone()

    def hide_site(self, site_id, name, kind):
        with self.connect() as conn:
            return conn.execute('''INSERT INTO sites(id,name,kind,hidden) VALUES (%s,%s,%s,true)
                ON CONFLICT (id) DO UPDATE SET hidden=true
                RETURNING id''', (site_id, name, kind)).fetchone()

    def delete_site(self, site_id):
        with self.connect() as conn:
            return conn.execute('DELETE FROM sites WHERE id=%s RETURNING id', (site_id,)).fetchone()

    def clear_messages(self, agent):
        with self.connect() as conn:
            cur = conn.execute('DELETE FROM conversation_messages WHERE agent_id=%s', (agent,))
            return cur.rowcount

class Message(BaseModel):
    content: str = Field(min_length=1, max_length=8000)

class SiteCreate(BaseModel):
    id: str = Field(min_length=2, max_length=32)
    name: str = Field(min_length=1, max_length=80)
    kind: str = Field(pattern='^(wordpress|vercel)$')
    url: str = Field(default='', max_length=300)


def create_app(settings=None, store=None, responder=None):
    settings = settings or Settings.from_env()
    store = store or Store(settings.database_url)
    security = HTTPBasic()
    responder = responder or (Responder(settings.api_key, settings.model) if settings.api_key else None)
    # Docker runs one worker. Reject simultaneous sends instead of interleaving turns.
    chat_locks = defaultdict(Lock)
    locks_guard = Lock()
    # Same single-worker scope as chat_locks. Conversation content stays in PostgreSQL.
    response_jobs = {}
    jobs_guard = Lock()
    daily_enabled = settings.daily_reports_enabled and isinstance(responder, Responder)

    def response_job(agent, job_id=None):
        with jobs_guard:
            cutoff = time.monotonic() - 3600
            for key, job in list(response_jobs.items()):
                if job['status'] != 'running' and job['updated'] < cutoff:
                    del response_jobs[key]
            if job_id is not None:
                job = response_jobs.get(job_id)
                return dict(job) if job and job['agent'] == agent else None
            for job in reversed(list(response_jobs.values())):
                if job['agent'] == agent and job['status'] == 'running':
                    return {'id': job['id'], 'status': job['status']}
        return None

    def monitor_targets():
        targets = {'usbestroofing': DEFAULT_MONITOR_URL}
        for sid, cfg in settings.wp_sites.items():
            if cfg.get('url'):
                targets[sid] = cfg['url']
        for sid, cfg in settings.git_sites.items():
            if cfg.get('site_url'):
                targets[sid] = cfg['site_url']
        list_fn = getattr(store, 'list_sites', None)
        if list_fn:
            for row in list_fn():
                if row.get('hidden'):
                    targets.pop(row['id'], None)
                    continue
                if row.get('url'):
                    targets[row['id']] = row['url']
        return list(targets.items())

    @asynccontextmanager
    async def lifespan(app):
        store.initialize()
        stop = Event()
        worker = None
        daily_worker = None
        if settings.monitor_enabled:
            def run():
                while not stop.is_set():
                    try:
                        store.check_if_due(monitor_targets())
                    except Exception:
                        logging.getLogger('mike.monitor').warning('Monitor check failed; will retry')
                    stop.wait(60)
            worker = Thread(target=run, daemon=True, name='availability-monitor')
            worker.start()
        if daily_enabled:
            def run_reports():
                while not stop.is_set():
                    try:
                        run_daily_report(store, responder, coordinator_context())
                    except Exception as exc:
                        logging.getLogger('mike.daily').error('Daily scheduler failed (%s)', type(exc).__name__)
                    stop.wait(30)
            daily_worker = Thread(target=run_reports, daemon=True, name='daily-reports')
            daily_worker.start()
        try:
            yield
        finally:
            stop.set()
            if worker:
                worker.join(timeout=12)
            if daily_worker:
                daily_worker.join(timeout=1)

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

    def all_agents():
        catalog = {'mike': {'id': 'mike', 'name': 'Mike', 'kind': 'system', 'custom': False}}
        for s in DEFAULT_SITES:
            catalog[s['id']] = {'id': s['id'], 'name': s['name'], 'kind': s['kind'], 'custom': False}
        for sid, cfg in settings.wp_sites.items():
            if sid not in catalog:
                catalog[sid] = {'id': sid, 'name': cfg.get('name', sid), 'kind': 'wordpress', 'url': cfg.get('url', ''), 'custom': False}
            elif cfg.get('url'):
                catalog[sid]['url'] = cfg['url']
        for sid, cfg in settings.ssh_sites.items():
            if sid not in catalog:
                catalog[sid] = {'id': sid, 'name': cfg.get('name', sid), 'kind': 'wordpress', 'custom': False}
        for sid, cfg in settings.git_sites.items():
            if sid not in catalog:
                catalog[sid] = {'id': sid, 'name': cfg.get('name', sid), 'kind': 'vercel', 'url': cfg.get('site_url', ''), 'custom': False}
            elif cfg.get('site_url'):
                catalog[sid]['url'] = cfg['site_url']
        list_fn = getattr(store, 'list_sites', None)
        hidden_ids = set()
        if list_fn:
            for row in list_fn():
                if row.get('hidden'):
                    hidden_ids.add(row['id'])
                    continue
                existing_url = catalog.get(row['id'], {}).get('url', '')
                catalog[row['id']] = {
                    'id': row['id'],
                    'name': row['name'],
                    'kind': row['kind'],
                    'url': row.get('url') or existing_url,
                    'custom': row['id'] not in SITE_DISPLAY_NAMES,
                }
        return [a for sid, a in catalog.items() if sid not in hidden_ids]

    def coordinator_context():
        def get_lock(site_id):
            with locks_guard:
                return chat_locks[site_id]
        return {
            'sites': [agent for agent in all_agents() if agent['id'] != 'mike'],
            'wp_sites': settings.wp_sites,
            'ssh_sites': settings.ssh_sites,
            'git_sites': settings.git_sites,
            'get_checks': getattr(store, 'latest_checks_by_site', None),
            'get_incidents': getattr(store, 'recent_incidents', None),
            'get_proposals': (lambda: store.list_proposals(limit=25)) if hasattr(store, 'list_proposals') else None,
            'get_messages': store.messages,
            'append_message': store.append,
            'proposal_creator': getattr(store, 'create_proposal', None),
            'get_lock': get_lock,
        }

    @app.get('/api/status', dependencies=[Depends(owner)])
    def status():
        store.ready()
        agents = all_agents()
        active_ids = {a['id'] for a in agents}
        site_checks = [c for c in getattr(store, 'latest_checks_by_site', lambda: [])() if c.get('site_id') in active_ids]
        incidents = [i for i in getattr(store, 'recent_incidents', lambda: [])() if i.get('site_id') in active_ids]
        has_execution = bool(settings.wp_sites or settings.git_sites)
        return {'database':'connected', 'ai':'configured' if responder else 'not_connected', 'telegram':'not_connected',
                'ssh':'read_only' if settings.ssh_sites else 'not_connected',
                'monitoring':'enabled' if settings.monitor_enabled else 'disabled', 'scan_interval_minutes':15,
                'daily_reports': {'enabled': daily_enabled, 'hour': REPORT_HOUR,
                                  'timezone': str(REPORT_TIMEZONE),
                                  'latest_run': getattr(store, 'latest_daily_report', lambda: None)()},
                'latest_check':store.latest_check(),
                'site_checks':site_checks,
                'incidents':incidents,
                'execution':'approval_required' if has_execution else 'disabled',
                'wp_sites':sorted(settings.wp_sites.keys()),
                'ssh_sites':sorted(settings.ssh_sites.keys()),
                'git_sites':sorted(settings.git_sites.keys()),
                'agents':agents}

    def check_agent(agent):
        if not any(a['id'] == agent for a in all_agents()):
            raise HTTPException(404, 'Unknown agent')

    @app.post('/api/sites', dependencies=[Depends(owner)], status_code=201)
    def add_site(body: SiteCreate):
        site_id = body.id.strip().lower()
        name = body.name.strip()
        url = body.url.strip()
        if site_id == 'mike' or not SITE_ID_RE.match(site_id):
            raise HTTPException(422, 'ID de sitio invalido (usa 2-32 letras minusculas, numeros, guiones).')
        if not name:
            raise HTTPException(422, 'Nombre requerido.')
        if url and not validate_public_http_url(url):
            raise HTTPException(422, 'URL invalida o no permitida (usa http(s) publico).')
        upsert_fn = getattr(store, 'upsert_site', None)
        if not upsert_fn:
            raise HTTPException(501, 'Site registry not available')
        try:
            site = upsert_fn(site_id, name, body.kind, url or None)
        except TypeError:
            site = upsert_fn(site_id, name, body.kind)
        if settings.monitor_enabled and url and hasattr(store, 'record_check'):
            def initial_scan():
                try:
                    store.record_check(site_id, url)
                except Exception:
                    logging.getLogger('mike.monitor').warning('Initial site check failed for %s', site_id)
            Thread(target=initial_scan, daemon=True, name=f'monitor-init-{site_id}').start()
        return {'site': site}

    @app.delete('/api/sites/{site_id}', dependencies=[Depends(owner)])
    def remove_site(site_id: str):
        if site_id == 'mike':
            raise HTTPException(400, 'Mike no se puede eliminar.')
        agents_map = {a['id']: a for a in all_agents()}
        target = agents_map.get(site_id)
        if not target:
            raise HTTPException(404, 'Sitio no encontrado')
        is_env_or_default = (
            site_id in SITE_DISPLAY_NAMES
            or site_id in settings.wp_sites
            or site_id in settings.ssh_sites
            or site_id in settings.git_sites
        )
        if is_env_or_default:
            hide_fn = getattr(store, 'hide_site', None)
            if not hide_fn:
                raise HTTPException(501, 'Site registry not available')
            hide_fn(site_id, target['name'], target['kind'])
            return {'deleted': site_id, 'hidden': True}
        delete_fn = getattr(store, 'delete_site', None)
        if not delete_fn:
            raise HTTPException(501, 'Site registry not available')
        deleted = delete_fn(site_id)
        if not deleted:
            raise HTTPException(404, 'Sitio no encontrado')
        return {'deleted': deleted['id'], 'hidden': False}

    @app.get('/api/agents/{agent}/messages', dependencies=[Depends(owner)])
    def messages(agent: str):
        check_agent(agent)
        return {'messages':store.messages(agent), 'response':response_job(agent)}

    @app.get('/api/agents/{agent}/responses/{job_id}', dependencies=[Depends(owner)])
    def response_status(agent: str, job_id: str):
        check_agent(agent)
        job = response_job(agent, job_id)
        if job is None:
            raise HTTPException(404, 'Response interrupted or expired; check the saved history')
        return {key: job[key] for key in ('id', 'status', 'result')}

    @app.delete('/api/agents/{agent}/messages', dependencies=[Depends(owner)])
    def clear_messages(agent: str):
        check_agent(agent)
        clear_fn = getattr(store, 'clear_messages', None)
        if not clear_fn:
            raise HTTPException(501, 'Clear chat not available')
        with locks_guard:
            lock = chat_locks[agent]
        if not lock.acquire(blocking=False):
            raise HTTPException(409, 'This chat already has a response in progress')
        try:
            removed = clear_fn(agent)
            return {'cleared': agent, 'deleted_count': removed}
        finally:
            lock.release()

    @app.post('/api/agents/{agent}/messages', dependencies=[Depends(owner)], status_code=201)
    def append(agent: str, body: Message, background: bool = False):
        check_agent(agent)
        text = body.content.strip()
        if not text:
            raise HTTPException(422, 'Message cannot be blank')
        with locks_guard:
            lock = chat_locks[agent]
        if not lock.acquire(blocking=False):
            raise HTTPException(409, 'This chat already has a response in progress')
        try:
            message = store.append(agent,text)
        except Exception:
            lock.release()
            raise

        def respond():
            result = {'message':message, 'ai':'not_connected'}
            if responder is not None:
                try:
                    if isinstance(responder, Responder):
                        coord_ctx = None
                        if agent == 'mike':
                            coord_ctx = coordinator_context()
                        answer = responder.reply(
                            agent,
                            store.messages(agent),
                            site_config=settings.wp_sites.get(agent),
                            proposal_creator=getattr(store, 'create_proposal', None),
                            ssh_config=settings.ssh_sites.get(agent),
                            git_config=settings.git_sites.get(agent),
                            coordinator_ctx=coord_ctx,
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

        if background and responder is not None:
            job_id = secrets.token_urlsafe(24)
            with jobs_guard:
                response_jobs[job_id] = {
                    'id': job_id, 'agent': agent, 'status': 'running',
                    'result': None, 'updated': time.monotonic(),
                }

            def run_response():
                try:
                    result = respond()
                except Exception as exc:
                    # Trace locations help diagnosis without exposing exception values/secrets.
                    frames = traceback.extract_tb(exc.__traceback__)
                    locations = ' > '.join(f'{Path(f.filename).name}:{f.lineno}:{f.name}' for f in frames)
                    logging.getLogger('mike.ai').error('Response %s failed (%s) at %s', job_id, type(exc).__name__, locations)
                    result = {'ai': 'unavailable', 'ai_error': 'backend',
                              'warning': f'Mensaje guardado. Falló el procesamiento del backend. [Diagnóstico: backend; referencia: {job_id}]'}
                finally:
                    lock.release()
                with jobs_guard:
                    response_jobs[job_id].update(
                        status='completed' if result.get('ai') == 'responded' else 'failed',
                        result={key: result[key] for key in ('ai', 'ai_error', 'warning') if key in result},
                        updated=time.monotonic(),
                    )

            try:
                Thread(target=run_response, daemon=True, name=f'chat-{agent}').start()
            except Exception:
                lock.release()
                with jobs_guard:
                    del response_jobs[job_id]
                raise
            return JSONResponse({'message': jsonable_encoder(message),
                                 'ai': 'pending', 'response_id': job_id}, status_code=202)

        try:
            return respond()
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
