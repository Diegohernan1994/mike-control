import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from threading import Event, Lock

import psycopg
import pytest
from fastapi.testclient import TestClient

from backend.ai import Responder
from backend.app import Settings, Store, create_app
from backend.daily_reports import REPORT_TIMEZONE, run_daily_report
from test_app import AUTH, SETTINGS, MemoryStore


class DailyStore(MemoryStore):
    def __init__(self):
        super().__init__()
        self.dates = set()
        self.finished = []

    def claim_daily_report(self, report_date):
        if report_date in self.dates:
            return False
        self.dates.add(report_date)
        return True

    def finish_daily_report(self, report_date, status, parts, summary):
        self.finished.append((report_date, status, parts, summary))


class ReportResponder:
    def __init__(self, count=2):
        self.calls = 0
        self.count = count

    def _exec_mike_tool(self, name, args, context):
        assert name == 'mike_ask_all_agents' and args == {}
        self.calls += 1
        reports = [{'site_id': f'site{i}', 'status': 'reported', 'report': 'a' * 3000}
                   for i in range(self.count)]
        reports.append({'site_id': 'offline', 'status': 'not_connected', 'report': 'Sin conexión'})
        return 'REPORTS\n' + json.dumps({'reports': reports})


def report_context(count=2):
    lock = Lock()
    return {'sites': [{'id': f'site{i}', 'name': f'Sitio {i}'} for i in range(count)],
            'get_lock': lambda agent: lock}


def test_runs_at_eight_argentina_once_per_day_and_keeps_all_site_results():
    store, responder, context = DailyStore(), ReportResponder(15), report_context(15)
    before = datetime(2026, 11, 17, 10, 59, 59, tzinfo=timezone.utc)
    assert not run_daily_report(store, responder, context, before)
    assert not responder.calls and not store.dates
    due = before + timedelta(seconds=1)
    assert run_daily_report(store, responder, context, due)
    assert responder.calls == 1
    report_date, status, parts, summary = store.finished[0]
    assert report_date == date(2026, 11, 17) and status == 'partial'
    assert summary['reported'] == 15 and summary['not_connected'] == 1
    assert all(0 < len(part) <= 8000 for part in parts)
    assert all(f'Sitio {i} —' in '\n'.join(parts) for i in range(15))
    assert 'offline — Sin conexión' in '\n'.join(parts)
    assert '08:00 (Argentina)' in parts[0]
    assert not run_daily_report(store, responder, context, due + timedelta(hours=1))
    assert run_daily_report(store, responder, context, due + timedelta(days=1))
    assert responder.calls == 2


def test_busy_chat_defers_without_claiming_or_spending_api():
    store, responder, context = DailyStore(), ReportResponder(), report_context()
    lock = context['get_lock']('mike')
    lock.acquire()
    now = datetime(2026, 11, 17, 8, tzinfo=REPORT_TIMEZONE)
    assert not run_daily_report(store, responder, context, now)
    assert not store.dates and not responder.calls
    lock.release()
    assert run_daily_report(store, responder, context, now)


def test_failure_records_safe_diagnosis_and_is_not_retried_after_restart(caplog):
    class Broken(ReportResponder):
        def _exec_mike_tool(self, *args):
            self.calls += 1
            raise RuntimeError('SECRET_API_KEY')

    store, responder, context = DailyStore(), Broken(), report_context()
    now = datetime(2026, 11, 17, 8, tzinfo=REPORT_TIMEZONE)
    assert run_daily_report(store, responder, context, now)
    assert store.finished[0][1] == 'failed'
    assert 'SECRET' not in str(store.finished) + caplog.text
    assert not run_daily_report(store, responder, report_context(), now)
    assert responder.calls == 1
    assert context['get_lock']('mike').acquire(blocking=False)


def test_server_configuration_enables_daily_schedule_and_allows_disabling(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'unused')
    monkeypatch.setenv('ADMIN_USERNAME', 'owner')
    monkeypatch.setenv('ADMIN_PASSWORD', SETTINGS.password)
    monkeypatch.delenv('DAILY_REPORTS_ENABLED', raising=False)
    assert Settings.from_env().daily_reports_enabled is True
    monkeypatch.setenv('DAILY_REPORTS_ENABLED', 'false')
    assert Settings.from_env().daily_reports_enabled is False


def test_lifespan_starts_daily_worker_and_reports_schedule_without_http_monitor(monkeypatch):
    started = Event()

    def fake_run(store, responder, context):
        assert any(site['id'] == 'usbestroofing' for site in context['sites'])
        assert context['get_lock']('mike') is context['get_lock']('mike')
        started.set()

    monkeypatch.setattr('backend.app.run_daily_report', fake_run)
    settings = replace(SETTINGS, daily_reports_enabled=True, monitor_enabled=False)
    with TestClient(create_app(settings, DailyStore(), Responder('fake', 'fake'))) as client:
        assert started.wait(2)
        assert client.get('/api/status').status_code == 401
        status = client.get('/api/status', auth=AUTH).json()
        assert status['monitoring'] == 'disabled'
        assert status['daily_reports'] == {
            'enabled': True, 'hour': 8, 'timezone': 'America/Argentina/Buenos_Aires', 'latest_run': None}


def test_real_postgres_claim_is_concurrent_durable_and_publication_is_atomic():
    url = os.environ.get('TEST_DATABASE_URL')
    if not url:
        pytest.skip('Requires isolated PostgreSQL')
    report_date = date(3000, 1, 1) + timedelta(days=uuid.uuid4().int % 365000)
    token = f'daily-integration-{uuid.uuid4()}'
    store = Store(url)
    store.initialize()
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: Store(url).claim_daily_report(report_date), range(2)))
        assert sorted(results) == [False, True]
        restarted = Store(url)
        restarted.initialize()
        assert not restarted.claim_daily_report(report_date)
        with pytest.raises(psycopg.errors.CheckViolation):
            restarted.finish_daily_report(report_date, 'completed', [token, 'x' * 8001], {'reported': 2})
        with store.connect() as conn:
            assert not conn.execute('SELECT id FROM conversation_messages WHERE content=%s', (token,)).fetchone()
            assert conn.execute('SELECT status FROM daily_reports WHERE report_date=%s', (report_date,)).fetchone()['status'] == 'running'
        restarted.finish_daily_report(report_date, 'completed', [token], {'reported': 1})
        restarted.finish_daily_report(report_date, 'completed', [token], {'reported': 1})
        with store.connect() as conn:
            rows = conn.execute('SELECT agent_id FROM conversation_messages WHERE content=%s', (token,)).fetchall()
            assert rows == [{'agent_id': 'mike'}]
        assert not any(row['content'] == token for row in restarted.messages('usbestroofing'))
        assert not Store(url).claim_daily_report(report_date)
    finally:
        with store.connect() as conn:
            conn.execute('DELETE FROM conversation_messages WHERE content=%s', (token,))
            conn.execute('DELETE FROM daily_reports WHERE report_date=%s', (report_date,))
