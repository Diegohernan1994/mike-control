import json
import time
from threading import Event, Lock

import pytest
from fastapi.testclient import TestClient

from backend.ai import AIUnavailable, Responder
from backend.app import create_app
from test_app import AUTH, HEADERS, SETTINGS, MemoryStore


def wait_for_job(client, job_id):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        job = client.get(f'/api/agents/mike/responses/{job_id}', auth=AUTH).json()
        if job['status'] != 'running':
            return job
        time.sleep(0.01)
    pytest.fail('Background response did not finish')


def test_background_acknowledges_before_ai_finishes_and_reload_resumes():
    started, release = Event(), Event()

    class Slow:
        def reply(self, *args):
            started.set()
            assert release.wait(5)
            return 'Informe terminado'

    store = MemoryStore()
    store.clear_messages = lambda agent: 0
    with TestClient(create_app(SETTINGS, store, Slow())) as client:
        try:
            result = client.post('/api/agents/mike/messages?background=true', auth=AUTH,
                                 headers=HEADERS, json={'content': 'Informe de todos'})
            assert result.status_code == 202
            assert started.wait(2)
            job_id = result.json()['response_id']
            history = client.get('/api/agents/mike/messages', auth=AUTH).json()
            assert history['response'] == {'id': job_id, 'status': 'running'}
            assert len(history['messages']) == 1
            assert client.post('/api/agents/mike/messages', auth=AUTH, headers=HEADERS,
                               json={'content': 'Duplicado'}).status_code == 409
            assert client.delete('/api/agents/mike/messages', auth=AUTH, headers=HEADERS).status_code == 409
            assert client.get(f'/api/agents/mike/responses/{job_id}').status_code == 401
            assert client.get(f'/api/agents/usbestroofing/responses/{job_id}', auth=AUTH).status_code == 404
        finally:
            release.set()
        assert wait_for_job(client, job_id)['status'] == 'completed'
        assert store.messages('mike')[-1]['content'] == 'Informe terminado'
        assert client.get('/api/agents/mike/messages', auth=AUTH).json()['response'] is None
    # A new process loses task status, while existing conversation data remains available.
    with TestClient(create_app(SETTINGS, store, Slow())) as restarted:
        assert restarted.get(f'/api/agents/mike/responses/{job_id}', auth=AUTH).status_code == 404
        assert len(restarted.get('/api/agents/mike/messages', auth=AUTH).json()['messages']) == 2


@pytest.mark.parametrize('exception,diagnosis', [
    (AIUnavailable('quota'), 'quota'),
    (ValueError('SECRET_PROVIDER_KEY'), 'backend'),
])
def test_background_failure_is_visible_safe_and_releases_chat(exception, diagnosis, caplog):
    class Broken:
        def reply(self, *args):
            raise exception

    store = MemoryStore()
    with TestClient(create_app(SETTINGS, store, Broken())) as client:
        result = client.post('/api/agents/mike/messages?background=true', auth=AUTH,
                             headers=HEADERS, json={'content': 'Informe'})
        job = wait_for_job(client, result.json()['response_id'])
        assert job['status'] == 'failed' and job['result']['ai_error'] == diagnosis
        assert 'SECRET' not in json.dumps(job) + caplog.text
        assert len(store.rows) == 1
        assert client.post('/api/agents/mike/messages', auth=AUTH, headers=HEADERS,
                           json={'content': '   '}).status_code == 422
        # The same chat can accept the next valid request after failure.
        next_result = client.post('/api/agents/mike/messages?background=true', auth=AUTH,
                                  headers=HEADERS, json={'content': 'Otra consulta'})
        assert next_result.status_code == 202
        assert wait_for_job(client, next_result.json()['response_id'])['status'] == 'failed'


def test_all_agents_are_reported_even_if_busy_unconnected_or_failing():
    store = MemoryStore()
    locks = {sid: Lock() for sid in ('ok', 'busy', 'fail')}
    locks['busy'].acquire()

    class Reports(Responder):
        def reply(self, agent, rows, **kwargs):
            assert kwargs['allow_proposals'] is False
            if agent == 'fail':
                raise AIUnavailable('timeout')
            assert agent == 'ok'
            return 'Estado observado por el agente'

    ctx = {
        'sites': [{'id': sid} for sid in ('ok', 'busy', 'fail', 'offline')],
        'wp_sites': {sid: {'url': 'https://example.com', 'bridge_secret': 'test'} for sid in locks},
        'get_lock': locks.get, 'get_messages': store.messages, 'append_message': store.append,
    }
    answer = Reports('fake', 'fake')._exec_mike_tool('mike_ask_all_agents', {}, ctx)
    reports = json.loads(answer.split('\n', 1)[1])['reports']
    assert [(r['site_id'], r['status']) for r in reports] == [
        ('ok', 'reported'), ('busy', 'failed'), ('fail', 'failed'), ('offline', 'not_connected')]
    assert store.messages('ok')[-1]['role'] == 'assistant'
    assert not store.messages('busy') and not store.messages('offline')
    assert locks['fail'].acquire(blocking=False)


def test_read_only_report_replays_reasoning_and_blocks_write_proposals():
    class ReadOnly(Responder):
        def __init__(self):
            super().__init__('fake', 'fake')
            self.calls = 0

        def _call_responses(self, instructions, items, tools):
            self.calls += 1
            if self.calls == 1:
                return {'output': [
                    {'type': 'reasoning', 'id': 'r1', 'summary': [], 'encrypted_content': 'opaque'},
                    {'type': 'function_call', 'call_id': 'c1', 'name': 'wp_toggle_plugin',
                     'arguments': '{"slug":"example","active":false}'},
                ]}
            assert items[-3]['type'] == 'reasoning'
            assert items[-2]['call_id'] == 'c1'
            assert 'error' in json.loads(items[-1]['output'])
            return {'output': [{'type': 'message', 'role': 'assistant',
                                'content': [{'type': 'output_text', 'text': 'Informe'}]}]}

    def reject_proposal(*args):
        pytest.fail('Read-only report attempted to create a proposal')

    assert ReadOnly().reply('example', [], site_config={'url': 'https://example.com', 'bridge_secret': 'test'},
                            proposal_creator=reject_proposal, allow_proposals=False) == 'Informe'
