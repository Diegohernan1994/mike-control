"""Lightweight, fixed-target availability checks; no browser or model calls."""
import ipaddress
import time
import urllib.error
import urllib.parse
import urllib.request

URL = 'https://usbestroofing.com/'
INTERVAL_SECONDS = 900


def validate_public_http_url(url):
    """Validate an HTTP(S) URL and reject loopback, private, or internal hostnames (SSRF guard)."""
    parsed = urllib.parse.urlparse((url or '').strip())
    if parsed.scheme not in ('http', 'https') or not parsed.hostname:
        return False
    host = parsed.hostname.lower().rstrip('.')
    if host == 'localhost' or host.endswith(('.localhost', '.local', '.internal')):
        return False
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            return False
    except ValueError:
        pass
    return True


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def probe(opener=None, url=URL):
    if not validate_public_http_url(url):
        return {'status': 'error', 'http_status': None, 'duration_ms': 0}
    opener = opener or urllib.request.build_opener(NoRedirect())
    request = urllib.request.Request(url, headers={'User-Agent': 'MikeControlMonitor/1.0', 'Accept': 'text/html'}, method='GET')
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
