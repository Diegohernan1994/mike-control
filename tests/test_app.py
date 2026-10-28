from datetime import datetime, timezone
import os
import pytest
import psycopg
from fastapi.testclient import TestClient
from backend.app import Settings, Store, create_app

SETTINGS = Settings('unused', 'owner', 'a-long-test-only-password-123456')
AUTH = (SETTINGS.username, SETTINGS.password)
HEADERS = {'X-Mike-Request':'1'}

class MemoryStore:
    def __init__(self):
        self.rows = []
    def initialize(self): pass
    def ready(self): pass
    def messages(self, agent):
        return [r for a,r in self.rows if a==agent][-100:]
    def append(self, agent, text, role="user"):
        row={'id':len(self.rows)+1,'role':role,'content':text,'created_at':datetime.now(timezone.utc)}
        self.rows.append((agent,row));return row

@pytest.fixture
def client():
    with TestClient(create_app(SETTINGS,MemoryStore())) as c:
        yield c

def test_requires_credentials(monkeypatch):
    for name in ('DATABASE_URL','ADMIN_USERNAME','ADMIN_PASSWORD'):
        monkeypatch.delenv(name,raising=False)
    with pytest.raises(RuntimeError): Settings.from_env()

@pytest.mark.parametrize('path',['/','/app.js','/api/status','/api/agents/mike/messages','/health/ready'])
def test_protected_routes(client,path):
    assert client.get(path).status_code==401
    assert client.get(path,auth=('owner','wrong')).status_code==401
    assert client.get(path,auth=AUTH).status_code==200

def test_cross_site_rejected_and_messages_isolated(client):
    path='/api/agents/mike/messages'
    assert client.post(path,auth=AUTH,json={'content':'hello'}).status_code==403
    assert client.post(path,auth=AUTH,headers={**HEADERS,'sec-fetch-site':'cross-site'},json={'content':'hello'}).status_code==403
    r=client.post(path,auth=AUTH,headers=HEADERS,json={'content':'  hello <script>  '})
    assert r.status_code==201
    assert r.json()['message']['content']=='hello <script>'
    assert len(client.get(path,auth=AUTH).json()['messages'])==1
    assert client.get('/api/agents/usbestroofing/messages',auth=AUTH).json()['messages']==[]
    assert client.get('/api/agents/unknown/messages',auth=AUTH).status_code==404
    assert client.post('/api/agents/unknown/messages',auth=AUTH,headers=HEADERS,json={'content':'hello'}).status_code==404

def test_validation_and_no_executor(client):
    path='/api/agents/mike/messages'
    for value in ('','   ','x'*8001):
        assert client.post(path,auth=AUTH,headers=HEADERS,json={'content':value}).status_code==422
    assert client.post(path,auth=AUTH,headers=HEADERS,content=b'x'*40001).status_code==413
    assert client.post('/api/execute',auth=AUTH,headers=HEADERS,json={}).status_code==404
    status=client.get('/api/status',auth=AUTH).json()
    assert status['execution']=='disabled'
    assert status['monitoring']=='not_implemented'
    assert status['ai']=='not_connected'

def test_database_errors_do_not_leak_credentials():
    class Broken(MemoryStore):
        def ready(self): raise psycopg.OperationalError('SECRET_DATABASE_PASSWORD')
    with TestClient(create_app(SETTINGS,Broken())) as c:
        r=c.get('/api/status',auth=AUTH)
        assert r.status_code==503
        assert 'SECRET' not in r.text

def test_no_cache_and_security_headers(client):
    r=client.get('/',auth=AUTH)
    assert r.headers['cache-control']=='no-store'
    assert "frame-ancestors 'none'" in r.headers['content-security-policy']
    assert 'localStorage' not in r.text

def test_postgres_persistence_and_restart():
    url=os.environ.get('TEST_DATABASE_URL')
    if not url: pytest.skip('Set TEST_DATABASE_URL to an isolated disposable PostgreSQL database')
    import uuid
    text='integration-'+str(uuid.uuid4())
    a=Store(url);a.initialize();a.initialize()
    try:
        a.append('mike',text)
        b=Store(url)
        assert any(m['content']==text for m in b.messages('mike'))
        assert not any(m['content']==text for m in b.messages('usbestroofing'))
        with TestClient(create_app(SETTINGS,b)) as c:
            assert c.get('/health/ready',auth=AUTH).status_code==200
            assert any(m['content']==text for m in c.get('/api/agents/mike/messages',auth=AUTH).json()['messages'])
    finally:
        with a.connect() as conn:
            conn.execute('DELETE FROM conversation_messages WHERE content=%s',(text,))
