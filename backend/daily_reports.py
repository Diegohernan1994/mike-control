"""Daily read-only agent reports, with one durable claim per Buenos Aires date."""
import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

REPORT_TIMEZONE = ZoneInfo('America/Argentina/Buenos_Aires')
REPORT_HOUR = 8


def run_daily_report(store, responder, context, now=None):
    local_now = (now or datetime.now(REPORT_TIMEZONE)).astimezone(REPORT_TIMEZONE)
    if local_now.hour < REPORT_HOUR:
        return False
    lock = context['get_lock']('mike')
    if not lock.acquire(blocking=False):
        return False
    try:
        report_date = local_now.date()
        if not store.claim_daily_report(report_date):
            return False
        try:
            raw = responder._exec_mike_tool('mike_ask_all_agents', {}, context)
            reports = json.loads(raw.split('\n', 1)[1])['reports']
            names = {site['id']: site.get('name', site['id']) for site in context['sites']}
            labels = {'reported': 'Informe del agente', 'failed': 'Consulta fallida',
                      'not_connected': 'Sin conexión'}
            heading = f'Informe diario — {local_now:%d/%m/%Y %H:%M} (Argentina)'
            parts = []
            current = heading
            for report in reports:
                site_id = report['site_id']
                label = labels.get(report['status'], 'Estado desconocido')
                block = f"\n\n{names.get(site_id, site_id)} — {label}\n{report['report']}"
                # Batch reports are capped at 3000 characters per site.
                if len(current) + len(block) > 7800:
                    parts.append(current)
                    current = heading + ' (continuación)'
                current += block
            if not reports:
                current += '\n\nNo hay sitios activos para informar.'
            parts.append(current)
            counts = {state: sum(r['status'] == state for r in reports) for state in labels}
            status = 'partial' if counts['failed'] or counts['not_connected'] else 'completed'
            store.finish_daily_report(report_date, status, parts, counts)
        except Exception as exc:
            # Do not log exception text, remote data, or credentials.
            logging.getLogger('mike.daily').error('Daily report failed (%s)', type(exc).__name__)
            store.finish_daily_report(report_date, 'failed', [
                f'Informe diario — {local_now:%d/%m/%Y} (Argentina)\n'
                'Falló la generación del informe. Los informes individuales que llegaron a '
                'guardarse siguen disponibles en sus chats. No se reintentará automáticamente hoy.'
            ], {'error': 'generation_failed'})
        return True
    finally:
        lock.release()
