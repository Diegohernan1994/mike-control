from fastapi.testclient import TestClient

from backend.app import Settings, create_app
from test_app import AUTH, HEADERS, MemoryStore


class DynamicMemoryStore(MemoryStore):
    def __init__(self):
        super().__init__()
        self.sites = {}

    def list_sites(self):
        return list(self.sites.values())

    def upsert_site(self, site_id, name, kind):
        row = {'id': site_id, 'name': name, 'kind': kind}
        self.sites[site_id] = row
        return row

    def delete_site(self, site_id):
        return self.sites.pop(site_id, None)


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

        # Add custom Vercel site
        r = c.post('/api/sites', auth=AUTH, headers=HEADERS, json={'id': 'modernroofing', 'name': 'Modern Roofing', 'kind': 'vercel'})
        assert r.status_code == 201
        agents = {a['id']: a for a in c.get('/api/status', auth=AUTH).json()['agents']}
        assert agents['modernroofing']['kind'] == 'vercel'
        assert agents['modernroofing']['custom'] is True

        # Chat works immediately for the new site
        assert c.post('/api/agents/modernroofing/messages', auth=AUTH, headers=HEADERS, json={'content': 'Hola'}).status_code == 201

        # Default sites cannot be deleted, custom site can
        assert c.delete('/api/sites/usbestroofing', auth=AUTH, headers=HEADERS).status_code == 400
        assert c.delete('/api/sites/modernroofing', auth=AUTH, headers=HEADERS).status_code == 200
        assert c.get('/api/agents/modernroofing/messages', auth=AUTH).status_code == 404
