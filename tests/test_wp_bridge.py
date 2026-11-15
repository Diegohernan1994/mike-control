import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from io import BytesIO

import pytest
from fastapi.testclient import TestClient

from backend.ai import Responder
from backend.app import Settings, create_app
from backend.wp_bridge import (
    BridgeError,
    is_read_only_call,
    params_hash,
    execute_remote_tool,
)
from test_app import AUTH, HEADERS, MemoryStore


class MemoryProposalStore(MemoryStore):
    def __init__(self):
        super().__init__()
        self.proposals = {}
        self._next_id = 1

    def create_proposal(self, site_id, tool_name, args, ttl_minutes=15):
        pid = self._next_id
        self._next_id += 1
        params = args or {}
        row = {
            'id': pid,
            'site_id': site_id,
            'tool_name': tool_name,
            'params_json': params,
            'params_hash': params_hash(tool_name, params),
            'status': 'pending',
            'expires_at': datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes),
            'created_at': datetime.now(timezone.utc),
            'executed_at': None,
            'result_json': None,
        }
        self.proposals[pid] = row
        return dict(row)

    def list_proposals(self, site_id=None, limit=50):
        now = datetime.now(timezone.utc)
        for row in self.proposals.values():
            if row['status'] == 'pending' and row['expires_at'] <= now:
                row['status'] = 'expired'
        rows = [dict(r) for r in self.proposals.values() if site_id is None or r['site_id'] == site_id]
        rows.sort(key=lambda r: r['id'], reverse=True)
        return rows[:limit]

    def get_proposal(self, proposal_id):
        row = self.proposals.get(proposal_id)
        return dict(row) if row else None

    def consume_proposal(self, proposal_id):
        row = self.proposals.get(proposal_id)
        if not row or row['status'] != 'pending' or row['expires_at'] <= datetime.now(timezone.utc):
            return None
        row['status'] = 'executing'
        return dict(row)

    def finish_proposal(self, proposal_id, status, result):
        row = self.proposals[proposal_id]
        row['status'] = status
        row['executed_at'] = datetime.now(timezone.utc)
        row['result_json'] = result
        return dict(row)

    def reject_proposal(self, proposal_id):
        row = self.proposals.get(proposal_id)
        if not row or row['status'] != 'pending':
            return None
        row['status'] = 'rejected'
        return dict(row)


def test_read_only_vs_write_classification():
    assert is_read_only_call('wp_get_site_overview', {}) is True
    assert is_read_only_call('wp_system_health_check', {}) is True
    assert is_read_only_call('wp_recent_changes', {'days': 7}) is True
    assert is_read_only_call('wp_get_activity_log', {'category': 'all'}) is True
    assert is_read_only_call('tutor_diagnose_course', {'auto_fix': False}) is True
    assert is_read_only_call('tutor_diagnose_course', {'auto_fix': True}) is False
    assert is_read_only_call('tutor_manage_enrollment', {'action': 'check'}) is True
    assert is_read_only_call('tutor_manage_enrollment', {'action': 'enroll'}) is False
    assert is_read_only_call('updraft_manage_backups', {'action': 'list'}) is True
    assert is_read_only_call('updraft_manage_backups', {'action': 'create'}) is False
    assert is_read_only_call('wp_manage_page', {'action': 'update', 'page_id': 5}) is False
    assert is_read_only_call('unknown_tool', {}) is False


def test_params_hash_deterministic():
    h1 = params_hash('wp_manage_page', {'b': 2, 'a': 1})
    h2 = params_hash('wp_manage_page', {'a': 1, 'b': 2})
    assert h1 == h2
    assert h1 != params_hash('wp_manage_page', {'a': 1, 'b': 3})


def test_hmac_signing_and_remote_execute(monkeypatch):
    captured = {}

    class FakeResp:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self, n): return json.dumps({'ok': True, 'data': {'site_name': 'Centro TAI'}}).encode()

    class FakeOpener:
        def open(self, req, timeout=45):
            captured['url'] = req.full_url
            captured['headers'] = {k.lower(): v for k, v in req.header_items()}
            captured['body'] = req.data
            return FakeResp()

    monkeypatch.setattr('backend.wp_bridge.urllib.request.build_opener', lambda *a: FakeOpener())
    secret = 'bridge-secret-123456'
    res = execute_remote_tool('https://centrotai.com/', secret, 'wp_get_site_overview', {})
    assert res['data']['site_name'] == 'Centro TAI'
    assert captured['url'] == 'https://centrotai.com/wp-json/ayrton-center/v1/remote-execute'
    ts = captured['headers']['x-ayrton-timestamp']
    sig = captured['headers']['x-ayrton-signature']
    expected = hmac.new(secret.encode(), f'{ts}.'.encode() + captured['body'], hashlib.sha256).hexdigest()
    assert hmac.compare_digest(sig, expected)


def test_ai_read_only_executes_and_write_creates_proposal(monkeypatch):
    responses = [
        {
            'status': 'completed',
            'output': [
                {
                    'type': 'function_call',
                    'call_id': 'call_1',
                    'name': 'wp_get_site_overview',
                    'arguments': '{}',
                },
                {
                    'type': 'function_call',
                    'call_id': 'call_2',
                    'name': 'updraft_manage_backups',
                    'arguments': '{"action":"create"}',
                },
            ],
        },
        {
            'status': 'completed',
            'output': [
                {
                    'type': 'message',
                    'role': 'assistant',
                    'content': [{'type': 'output_text', 'text': 'Sitio verificado y respaldo propuesto.'}],
                }
            ],
        },
    ]

    class SeqOpener:
        def __init__(self):
            self.calls = []
        def open(self, req, timeout):
            idx = len(self.calls)
            self.calls.append(json.loads(req.data))
            return BytesIO(json.dumps(responses[idx]).encode())

    remote_calls = []
    monkeypatch.setattr(
        'backend.ai.execute_remote_tool',
        lambda url, secret, tool, args: (remote_calls.append((tool, args)) or {'wp_version': '6.7'}),
    )

    proposals = []
    def fake_creator(site_id, tool_name, args):
        p = {
            'id': len(proposals) + 1,
            'site_id': site_id,
            'tool_name': tool_name,
            'params_json': args,
            'status': 'pending',
            'expires_at': datetime.now(timezone.utc) + timedelta(minutes=15),
        }
        proposals.append(p)
        return p

    ai = Responder('secret-key', 'gpt-5-mini')
    ai.opener = SeqOpener()
    reply = ai.reply(
        'centrotai',
        [{'role': 'user', 'content': 'Revisa el sitio y crea un respaldo'}],
        site_config={'url': 'https://centrotai.com', 'bridge_secret': 's3cr3t', 'name': 'Centro TAI'},
        proposal_creator=fake_creator,
    )
    assert reply == 'Sitio verificado y respaldo propuesto.'
    assert remote_calls == [('wp_get_site_overview', {})]
    assert len(proposals) == 1
    assert proposals[0]['tool_name'] == 'updraft_manage_backups'
    assert proposals[0]['site_id'] == 'centrotai'
    assert len(ai.opener.calls[0]['tools']) > 0


def test_proposals_single_use_approve_reject_and_expiry(monkeypatch):
    settings = Settings(
        'unused',
        'owner',
        'a-long-test-only-password-123456',
        wp_sites={'centrotai': {'url': 'https://centrotai.com', 'bridge_secret': 's3cr3t', 'name': 'Centro TAI'}},
    )
    store = MemoryProposalStore()
    executed = []
    monkeypatch.setattr(
        'backend.app.execute_remote_tool',
        lambda url, secret, tool, args: (executed.append((url, tool, args)) or {'ok': True}),
    )

    with TestClient(create_app(settings, store)) as c:
        p1 = store.create_proposal('centrotai', 'updraft_manage_backups', {'action': 'create'})
        p2 = store.create_proposal('centrotai', 'wp_manage_page', {'action': 'update', 'page_id': 9})
        p_exp = store.create_proposal('centrotai', 'updraft_manage_backups', {'action': 'create'}, ttl_minutes=-1)
        p_other = store.create_proposal('usbestroofing', 'updraft_manage_backups', {'action': 'create'})

        # Listing includes proposals
        r = c.get('/api/proposals', auth=AUTH)
        assert r.status_code == 200
        assert len(r.json()['proposals']) == 4

        # Approve p1 succeeds once
        r = c.post(f"/api/proposals/{p1['id']}/approve", auth=AUTH, headers=HEADERS)
        assert r.status_code == 200
        assert r.json()['proposal']['status'] == 'executed'
        assert len(executed) == 1

        # Double-use of p1 is rejected with 409
        r2 = c.post(f"/api/proposals/{p1['id']}/approve", auth=AUTH, headers=HEADERS)
        assert r2.status_code == 409
        assert len(executed) == 1

        # Reject p2 works once, then 409
        assert c.post(f"/api/proposals/{p2['id']}/reject", auth=AUTH, headers=HEADERS).status_code == 200
        assert c.post(f"/api/proposals/{p2['id']}/approve", auth=AUTH, headers=HEADERS).status_code == 409

        # Expired proposal cannot be approved
        assert c.post(f"/api/proposals/{p_exp['id']}/approve", auth=AUTH, headers=HEADERS).status_code == 409

        # Site without WP bridge configured returns 400
        assert c.post(f"/api/proposals/{p_other['id']}/approve", auth=AUTH, headers=HEADERS).status_code == 400
