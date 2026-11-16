from fastapi.testclient import TestClient

from backend.app import Settings, create_app
from test_app import AUTH, HEADERS, MemoryStore


class DynamicMemoryStore(MemoryStore):
    def __init__(self):
        super().__init__()
        self.sites = {}
        self.checks = []

    def list_sites(self):
        return list(self.sites.values())

    def upsert_site(self, site_id, name, kind, url=None):
        row = {'id': site_id, 'name': name, 'kind': kind, 'url': url, 'hidden': False}
        self.sites[site_id] = row
        return row

    def hide_site(self, site_id, name, kind):
        existing = self.sites.get(site_id, {})
        row = {'id': site_id, 'name': existing.get('name', name), 'kind': existing.get('kind', kind), 'url': existing.get('url'), 'hidden': True}
        self.sites[site_id] = row
        return row

    def delete_site(self, site_id):
        return self.sites.pop(site_id, None)

    def clear_messages(self, agent):
        before = len(self.rows)
        self.rows = [(a, r) for a, r in self.rows if a != agent]
        return before - len(self.rows)

    def record_check(self, site_id, url):
        row = {'site_id': site_id, 'url': url, 'status': 'ok', 'http_status': 200, 'duration_ms': 15}
        self.checks.append(row)
        return row

    def latest_checks_by_site(self):
        return list(self.checks)

    def recent_incidents(self):
        return []


def test_env_auto_discovery_for_wp_and_vercel(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql://unused')
    monkeypatch.setenv('ADMIN_USERNAME', 'owner')
    monkeypatch.setenv('ADMIN_PASSWORD', 'a-long-test-only-password-123456')
    monkeypatch.setenv('EXODUS_WP_URL', 'https://exodusremodeling.com')
    monkeypatch.setenv('EXODUS_WP_BRIDGE_SECRET', 'secret-exodus-123')
    monkeypatch.setenv('EXODUS_SITE_NAME', 'Exodus Remodeling')
    monkeypatch.setenv('LANDINGX_GITHUB_REPO', 'org/landing-x')
    monkeypatch.setenv('LANDINGX_GITHUB_TOKEN', 'ghp_landingx')

    settings = Settings.from_env()
    assert 'exodus' in settings.wp_sites
    assert settings.wp_sites['exodus']['name'] == 'Exodus Remodeling'
    assert 'landingx' in settings.git_sites
    assert settings.git_sites['landingx']['name'] == 'Landingx'

    with TestClient(create_app(settings, DynamicMemoryStore())) as c:
        agents = {a['id']: a for a in c.get('/api/status', auth=AUTH).json()['agents']}
        assert agents['exodus']['kind'] == 'wordpress'
        assert agents['landingx']['kind'] == 'vercel'
        assert c.post('/api/agents/exodus/messages', auth=AUTH, headers=HEADERS, json={'content': 'Hola'}).status_code == 201


def test_add_and_remove_custom_sites_via_api():
    settings = Settings('unused', 'owner', 'a-long-test-only-password-123456')
    store = DynamicMemoryStore()

    with TestClient(create_app(settings, store)) as c:
        # Reject invalid IDs and reserved 'mike'
        assert c.post('/api/sites', auth=AUTH, headers=HEADERS, json={'id': 'mike', 'name': 'Mike 2', 'kind': 'wordpress'}).status_code == 422
        assert c.post('/api/sites', auth=AUTH, headers=HEADERS, json={'id': 'BAD ID!', 'name': 'Bad', 'kind': 'vercel'}).status_code == 422

        # Invalid and internal/SSRF URLs rejected
        assert c.post('/api/sites', auth=AUTH, headers=HEADERS, json={'id': 'badurl', 'name': 'Bad', 'kind': 'vercel', 'url': 'ftp://x.com'}).status_code == 422
        assert c.post('/api/sites', auth=AUTH, headers=HEADERS, json={'id': 'ssrf1', 'name': 'SSRF', 'kind': 'vercel', 'url': 'http://127.0.0.1:8000'}).status_code == 422
        assert c.post('/api/sites', auth=AUTH, headers=HEADERS, json={'id': 'ssrf2', 'name': 'SSRF2', 'kind': 'vercel', 'url': 'http://169.254.169.254/latest/meta-data/'}).status_code == 422
        assert c.post('/api/sites', auth=AUTH, headers=HEADERS, json={'id': 'ssrf3', 'name': 'SSRF3', 'kind': 'vercel', 'url': 'http://localhost:3000'}).status_code == 422

        # Add custom Vercel site with monitoring URL
        r = c.post('/api/sites', auth=AUTH, headers=HEADERS, json={'id': 'modernroofing', 'name': 'Modern Roofing', 'kind': 'vercel', 'url': 'https://modernroofing.example'})
        assert r.status_code == 201
        assert r.json()['site']['url'] == 'https://modernroofing.example'
        agents = {a['id']: a for a in c.get('/api/status', auth=AUTH).json()['agents']}
        assert agents['modernroofing']['kind'] == 'vercel'
        assert agents['modernroofing']['custom'] is True

        # Chat works immediately for the new site and can be cleared
        assert c.post('/api/agents/modernroofing/messages', auth=AUTH, headers=HEADERS, json={'content': 'Hola'}).status_code == 201
        assert len(c.get('/api/agents/modernroofing/messages', auth=AUTH).json()['messages']) >= 1
        assert c.delete('/api/agents/modernroofing/messages', auth=AUTH, headers=HEADERS).status_code == 200
        assert c.get('/api/agents/modernroofing/messages', auth=AUTH).json()['messages'] == []
        assert c.delete('/api/agents/unknown/messages', auth=AUTH, headers=HEADERS).status_code == 404

        # Edit existing site updates name, kind, url in /api/status
        edit_res = c.post('/api/sites', auth=AUTH, headers=HEADERS, json={'id': 'modernroofing', 'name': 'Modern Roofing Pro', 'kind': 'wordpress', 'url': 'https://modernroofing.com'})
        assert edit_res.status_code == 201
        agents = {a['id']: a for a in c.get('/api/status', auth=AUTH).json()['agents']}
        assert agents['modernroofing']['name'] == 'Modern Roofing Pro'
        assert agents['modernroofing']['kind'] == 'wordpress'
        assert agents['modernroofing']['url'] == 'https://modernroofing.com'

        # 'mike' cannot be deleted, base site can be hidden and restored, custom site can be deleted
        assert c.delete('/api/sites/mike', auth=AUTH, headers=HEADERS).status_code == 400
        assert c.delete('/api/sites/usbestroofing', auth=AUTH, headers=HEADERS).status_code == 200
        assert 'usbestroofing' not in {a['id'] for a in c.get('/api/status', auth=AUTH).json()['agents']}
        assert c.get('/api/agents/usbestroofing/messages', auth=AUTH).status_code == 404
        assert c.post('/api/sites', auth=AUTH, headers=HEADERS, json={'id': 'usbestroofing', 'name': 'US Best Roofing', 'kind': 'wordpress', 'url': 'https://usbestroofing.com'}).status_code == 201
        assert 'usbestroofing' in {a['id'] for a in c.get('/api/status', auth=AUTH).json()['agents']}

        assert c.delete('/api/sites/modernroofing', auth=AUTH, headers=HEADERS).status_code == 200
        assert c.get('/api/agents/modernroofing/messages', auth=AUTH).status_code == 404


def test_bilingual_ui_assets_served():
    settings = Settings('unused', 'owner', 'a-long-test-only-password-123456')
    with TestClient(create_app(settings, DynamicMemoryStore())) as c:
        html = c.get('/', auth=AUTH).text
        assert 'data-lang="es"' in html
        assert 'data-lang="en"' in html
        js = c.get('/app.js', auth=AUTH).text
        assert "I18N" in js
        assert "en-US" in js
        assert "view('Resumen')" in js


def test_mike_coordinator_tools(monkeypatch):
    from backend.ai import Responder
    settings = Settings('unused', 'owner', 'a-long-test-only-password-123456')
    store = DynamicMemoryStore()
    store.upsert_site('exodus', 'Exodus', 'wordpress', 'https://exodusremodeling.com')
    store.record_check('exodus', 'https://exodusremodeling.com')
    store.append('exodus', 'El sitio esta online sin errores', role='assistant')

    proposals = []
    def fake_create_proposal(site_id, tool_name, args):
        p = {'id': len(proposals) + 1, 'site_id': site_id, 'tool_name': tool_name, 'params_json': args, 'status': 'pending', 'expires_at': '2030-01-01T00:00:00Z'}
        proposals.append(p)
        return p

    responder = Responder('sk-test', 'gpt-4o-mini')
    calls = []
    def fake_call(instructions, input_items, tools):
        calls.append([t['name'] for t in tools])
        if len(calls) == 1:
            return {'output': [{'type': 'function_call', 'call_id': 'c1', 'name': 'mike_overview', 'arguments': '{}'}]}
        if len(calls) == 2:
            return {'output': [{'type': 'function_call', 'call_id': 'c2', 'name': 'mike_read_agent_chat', 'arguments': '{"site_id":"exodus"}'}]}
        if len(calls) == 3:
            return {'output': [{'type': 'function_call', 'call_id': 'c3', 'name': 'mike_propose_site_action', 'arguments': '{"site_id":"exodus","tool_name":"updraft_manage_backups","args_json":"{\\"action\\":\\"create\\"}"}'}]}
        return {'output': [{'type': 'message', 'role': 'assistant', 'content': [{'type': 'output_text', 'text': 'Informe completo verificado.'}]}]}

    monkeypatch.setattr(responder, '_call_responses', fake_call)
    ctx = {
        'sites': [{'id': 'exodus', 'name': 'Exodus', 'kind': 'wordpress', 'url': 'https://exodusremodeling.com'}],
        'wp_sites': {'exodus': {'name': 'Exodus', 'url': 'https://exodusremodeling.com', 'bridge_secret': 'sec'}},
        'ssh_sites': {},
        'git_sites': {},
        'get_checks': store.latest_checks_by_site,
        'get_incidents': store.recent_incidents,
        'get_proposals': lambda: proposals,
        'get_messages': store.messages,
        'append_message': store.append,
        'proposal_creator': fake_create_proposal,
        'get_lock': None,
    }
    reply = responder.reply('mike', [{'role': 'user', 'content': 'Dame informe y crea backup en exodus'}], coordinator_ctx=ctx)
    assert reply == 'Informe completo verificado.'
    assert 'mike_overview' in calls[0]
    assert 'mike_ask_agent' in calls[0]
    assert len(proposals) == 1 and proposals[0]['site_id'] == 'exodus' and proposals[0]['tool_name'] == 'updraft_manage_backups'
    # Disallowed / unknown write tool is rejected
    bad_res = responder._exec_mike_tool('mike_propose_site_action', {'site_id': 'exodus', 'tool_name': 'evil_shell', 'args_json': '{}'}, ctx)
    assert 'no permitida' in bad_res
