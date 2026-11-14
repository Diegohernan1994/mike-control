import base64
import json
from datetime import datetime, timedelta, timezone
from io import BytesIO

import pytest
from fastapi.testclient import TestClient

from backend.ai import Responder
from backend.app import Settings, create_app
from backend.git_bridge import (
    GitBridgeError,
    execute_git_proposal,
    execute_git_read_tool,
    is_git_read_only_call,
    sanitize_repo_path,
)
from backend.ssh_reader import (
    SSHError,
    _load_host_key,
    execute_ssh_read_tool,
    is_ssh_read_only_call,
    sanitize_ssh_rel_path,
)
from test_app import AUTH, HEADERS
from test_wp_bridge import MemoryProposalStore


@pytest.mark.parametrize(
    'bad_path',
    ['../.env', '.env', '.env.production', 'config/secrets.json', '.git/config', 'node_modules/pkg/index.js', 'certs/key.pem', 'dump.sql'],
)
def test_git_sensitive_paths_blocked(bad_path):
    with pytest.raises(GitBridgeError):
        sanitize_repo_path(bad_path)


def test_git_read_file_and_propose_branch_pr(monkeypatch):
    calls = []

    def fake_gh(token, method, path, body=None, timeout=30):
        calls.append((method, path, body))
        if method == 'GET' and '/contents/src/pages/index.astro' in path:
            encoded = base64.b64encode(b'line1\nline2\nline3\n').decode('ascii')
            return {'type': 'file', 'size': 18, 'sha': 'oldsha', 'content': encoded}
        if method == 'GET' and '/git/ref/heads/main' in path:
            return {'object': {'sha': 'basesha123'}}
        if method == 'POST' and path.endswith('/git/refs'):
            return {'ref': body['ref']}
        if method == 'PUT' and '/contents/src/pages/index.astro' in path:
            return {'commit': {'sha': 'commitsha456'}}
        if method == 'POST' and path.endswith('/pulls'):
            return {'number': 42, 'html_url': 'https://github.com/org/pacific/pull/42'}
        return {}

    monkeypatch.setattr('backend.git_bridge._github_request', fake_gh)
    cfg = {'repo': 'org/pacific', 'github_token': 'ghp_test', 'branch': 'main'}

    res = execute_git_read_tool(cfg, 'git_read_file', {'path': 'src/pages/index.astro', 'start_line': 2, 'max_lines': 2})
    assert res['content'] == 'line2\nline3'

    pr = execute_git_proposal(
        cfg,
        proposal_id=7,
        tool_name='git_propose_file_change',
        args={
            'path': 'src/pages/index.astro',
            'content': '<h1>Nuevo</h1>',
            'commit_message': 'Update hero',
            'pr_title': 'Update hero on Pacific',
        },
    )
    assert pr['branch'] == 'mike/prop-7'
    assert pr['pr_number'] == 42
    assert pr['pr_url'] == 'https://github.com/org/pacific/pull/42'
    # Verify commit targeted feature branch, never main
    put_call = [c for c in calls if c[0] == 'PUT'][0]
    assert put_call[2]['branch'] == 'mike/prop-7'


@pytest.mark.parametrize(
    'bad_path',
    ['../etc/passwd', 'wp-config.php', 'wp-config-sample.php', '.env', '.env.local', 'db/backup.sql', 'ssl/priv.key', 'id_rsa'],
)
def test_ssh_sensitive_paths_and_traversal_blocked(bad_path):
    with pytest.raises(SSHError):
        sanitize_ssh_rel_path('/var/www/html', bad_path, allow_empty=False)


def test_ssh_requires_pinned_host_key():
    with pytest.raises(SSHError):
        _load_host_key('')
    with pytest.raises(SSHError):
        _load_host_key('ssh-ed25519')


def test_ssh_read_tools_and_filtering(monkeypatch):
    cmds = []

    def fake_run(cfg, cmd, timeout=20, max_bytes=32768):
        cmds.append(cmd)
        if cmd.startswith('ls -la'):
            return {'exit_code': 0, 'stdout': 'index.php\nwp-config.php\n.env\nwp-content\n', 'stderr': '', 'truncated': False}
        if cmd.startswith('sed -n'):
            return {'exit_code': 0, 'stdout': '<?php // theme', 'stderr': '', 'truncated': False}
        return {'exit_code': 0, 'stdout': 'Success: WordPress installation verifies against checksums.', 'stderr': '', 'truncated': False}

    monkeypatch.setattr('backend.ssh_reader._run_readonly_command', fake_run)
    cfg = {'host': '1.2.3.4', 'username': 'wp_ro', 'private_key': 'k', 'host_key': 'ssh-ed25519 AAA', 'root_path': '/var/www/html'}

    listing = execute_ssh_read_tool(cfg, 'ssh_list_dir', {'rel_path': ''})
    assert 'wp-config.php' not in listing['entries']
    assert '.env' not in listing['entries']
    assert 'wp-content' in listing['entries']

    file_out = execute_ssh_read_tool(cfg, 'ssh_read_file', {'rel_path': 'wp-content/themes/x/functions.php', 'start_line': 1, 'max_lines': 10})
    assert '<?php' in file_out['content']

    chk = execute_ssh_read_tool(cfg, 'ssh_wp_verify_checksums', {})
    assert chk['exit_code'] == 0
    assert is_ssh_read_only_call('ssh_read_file') is True
    assert is_git_read_only_call('git_propose_file_change') is False


def test_pacific_ai_flow_and_single_use_git_approval(monkeypatch):
    responses = [
        {
            'status': 'completed',
            'output': [
                {'type': 'function_call', 'call_id': 'c1', 'name': 'git_list_files', 'arguments': '{"path":"src"}'},
                {
                    'type': 'function_call',
                    'call_id': 'c2',
                    'name': 'git_propose_file_change',
                    'arguments': json.dumps({
                        'path': 'src/pages/index.astro',
                        'content': '<main>Hola Pacific</main>',
                        'commit_message': 'Update copy',
                        'pr_title': 'Update Pacific copy',
                    }),
                },
            ],
        },
        {
            'status': 'completed',
            'output': [
                {'type': 'message', 'role': 'assistant', 'content': [{'type': 'output_text', 'text': 'Propuesta creada para Pacific.'}]}
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

    monkeypatch.setattr('backend.ai.execute_git_read_tool', lambda cfg, tool, args: {'entries': ['pages']})
    monkeypatch.setattr(
        'backend.app.execute_git_proposal',
        lambda cfg, pid, tool, args: {'branch': f'mike/prop-{pid}', 'pr_number': 11, 'pr_url': 'https://github.com/org/pacific/pull/11'},
    )

    settings = Settings(
        'unused',
        'owner',
        'a-long-test-only-password-123456',
        git_sites={'pacific': {'repo': 'org/pacific', 'github_token': 'ghp_test', 'branch': 'main', 'name': 'Pacific'}},
    )
    store = MemoryProposalStore()
    ai = Responder('secret', 'gpt-5-mini')
    ai.opener = SeqOpener()

    with TestClient(create_app(settings, store, ai)) as c:
        r = c.post('/api/agents/pacific/messages', auth=AUTH, headers=HEADERS, json={'content': 'Actualiza el home'})
        assert r.status_code == 201
        assert r.json()['reply']['content'] == 'Propuesta creada para Pacific.'

        props = c.get('/api/proposals?site_id=pacific', auth=AUTH).json()['proposals']
        assert len(props) == 1
        pid = props[0]['id']

        ok = c.post(f'/api/proposals/{pid}/approve', auth=AUTH, headers=HEADERS)
        assert ok.status_code == 200
        assert ok.json()['result']['pr_number'] == 11

        # Second approval must fail (single-use)
        assert c.post(f'/api/proposals/{pid}/approve', auth=AUTH, headers=HEADERS).status_code == 409

        # Site isolation: gabriels git proposal cannot execute without gabriels config
        p_other = store.create_proposal('gabriels', 'git_propose_file_change', {'path': 'a.txt', 'content': 'x'})
        assert c.post(f"/api/proposals/{p_other['id']}/approve", auth=AUTH, headers=HEADERS).status_code == 400
