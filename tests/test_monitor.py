import io
import urllib.error
from backend.monitor import probe


class Response:
    status = 200
    def __enter__(self): return self
    def __exit__(self, *args): pass


class Opener:
    def __init__(self, result): self.result = result
    def open(self, request, timeout):
        assert request.full_url == 'https://usbestroofing.com/'
        assert request.method == 'GET' and timeout == 10
        if isinstance(self.result, Exception): raise self.result
        return self.result


def test_availability_and_redirect_and_failure():
    assert probe(Opener(Response()))['status'] == 'ok'
    redirect = urllib.error.HTTPError('https://usbestroofing.com/', 301, 'redirect', {}, io.BytesIO())
    assert probe(Opener(redirect))['status'] == 'redirect'
    failure = urllib.error.HTTPError('https://usbestroofing.com/', 503, 'error', {}, io.BytesIO())
    assert probe(Opener(failure))['http_status'] == 503
    assert probe(Opener(urllib.error.URLError('offline')))['status'] == 'error'
