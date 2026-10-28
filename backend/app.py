"""First backend milestone: protected dashboard and durable conversation archive.
Optional conversational AI; no SSH, scheduler or execution tools.
"""
import logging
import os
import secrets
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from threading import Lock
from backend.ai import Responder, AIUnavailable
from pathlib import Path
from typing import Annotated

import psycopg
from psycopg.rows import dict_row
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
AGENTS = ('mike', 'usbestroofing')

@dataclass(frozen=True)
class Settings:
    database_url: str
    username: str
    password: str = field(repr=False)
    api_key: str = field(default="", repr=False)
    model: str = "gpt-5-mini"

    @classmethod
    def from_env(cls):
        values = [os.environ.get(k, '') for k in ('DATABASE_URL', 'ADMIN_USERNAME', 'ADMIN_PASSWORD')]
        if not all(values) or len(values[2]) < 24:
            raise RuntimeError('Set DATABASE_URL, ADMIN_USERNAME and ADMIN_PASSWORD (24+ characters).')
        return cls(*values, api_key=os.environ.get("OPENAI_API_KEY", "").strip(),
                   model=os.environ.get("OPENAI_MODEL", "gpt-5-mini").strip())

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
            # Upgrade the original role constraint transactionally without deleting history.
            conn.execute('ALTER TABLE conversation_messages DROP CONSTRAINT IF EXISTS conversation_messages_role_check')
            conn.execute("ALTER TABLE conversation_messages ADD CONSTRAINT conversation_messages_role_check CHECK(role IN ('user','system','assistant'))")
            conn.execute('''CREATE INDEX IF NOT EXISTS messages_agent_id_idx
                ON conversation_messages(agent_id, id DESC)''')

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
        yield

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
        return {'database':'connected', 'ai':'configured' if responder else 'not_connected', 'telegram':'not_connected',
                'ssh':'not_connected', 'monitoring':'not_implemented', 'scan_interval_minutes':15,
                'execution':'disabled', 'agents':[{'id':'mike','name':'Mike'},
                    {'id':'usbestroofing','name':'US Best Roofing'}]}

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

    return app
