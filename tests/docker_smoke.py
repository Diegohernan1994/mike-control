"""Run only on a disposable Docker CI runner with TEST_DATABASE_URL set."""
import base64
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
import uuid

NAME='mike-control-smoke'
PASSWORD='isolated-ci-owner-password-123456'
AUTH='Basic '+base64.b64encode(('owner:'+PASSWORD).encode()).decode()
BASE='http://127.0.0.1:8000'

def request(path, payload=None, auth=True):
    headers={'X-Mike-Request':'1','Content-Type':'application/json'}
    if auth: headers['Authorization']=AUTH
    data=None if payload is None else json.dumps(payload).encode()
    with urllib.request.urlopen(urllib.request.Request(BASE+path,data=data,headers=headers),timeout=5) as r:
        return r.read()

def ready():
    for _ in range(40):
        try:
            assert json.loads(request('/health/ready'))['status']=='ready'
            return
        except (urllib.error.URLError, AssertionError): time.sleep(1)
    raise RuntimeError('Packaged application failed readiness check')

if __name__=='__main__':
    url=os.environ['TEST_DATABASE_URL']
    env={**os.environ,'DATABASE_URL':url,'ADMIN_USERNAME':'owner','ADMIN_PASSWORD':PASSWORD}
    subprocess.run(['docker','run','-d','--name',NAME,'--network','host',
        '-e','DATABASE_URL','-e','ADMIN_USERNAME','-e','ADMIN_PASSWORD','mike-control:verify'],env=env,check=True)
    try:
        ready()
        try:
            request('/',auth=False)
            raise AssertionError('Dashboard exposed without credentials')
        except urllib.error.HTTPError as e: assert e.code==401
        assert b'/app.js' in request('/')
        assert b"view('Resumen')" in request('/app.js')
        text='docker-smoke-'+str(uuid.uuid4())
        request('/api/agents/mike/messages',{'content':text})
        subprocess.run(['docker','restart',NAME],check=True)
        ready()
        rows=json.loads(request('/api/agents/mike/messages'))['messages']
        assert any(r['content']==text for r in rows)
        other=json.loads(request('/api/agents/usbestroofing/messages'))['messages']
        assert not any(r['content']==text for r in other)
        print('Docker: authentication, assets, PostgreSQL and restart persistence passed.')
    finally:
        subprocess.run(['docker','rm','-f',NAME],check=False)
