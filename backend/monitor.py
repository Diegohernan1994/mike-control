"""Lightweight, fixed-target availability checks; no browser or model calls."""
import time
import urllib.error
import urllib.request

URL = 'https://usbestroofing.com/'
INTERVAL_SECONDS = 900


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def probe(opener=None):
    opener = opener or urllib.request.build_opener(NoRedirect())
    request = urllib.request.Request(URL, headers={'User-Agent': 'MikeControlMonitor/1.0', 'Accept': 'text/html'}, method='GET')
    start = time.monotonic()
    try:
        with opener.open(request, timeout=10) as response:
            code = response.status
    except urllib.error.HTTPError as exc:
        code = exc.code
        exc.close()
    except (urllib.error.URLError, TimeoutError, OSError):
        return {'status': 'error', 'http_status': None, 'duration_ms': round((time.monotonic()-start)*1000)}
    return {'status': 'ok' if 200 <= code < 300 else 'redirect' if 300 <= code < 400 else 'error',
            'http_status': code, 'duration_ms': round((time.monotonic()-start)*1000)}
