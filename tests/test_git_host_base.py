import pytest

from runtime.git_host.base import GitHost, HostError

FAKE = "fake-secret-token-12345"


class _Resp:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body

    def json(self):
        return self._body


class _Session:
    def __init__(self, status=200, body=None, raise_exc=None):
        self.status = status
        self.body = body or {}
        self.raise_exc = raise_exc
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if self.raise_exc:
            raise self.raise_exc
        return _Resp(self.status, self.body)


class _Concrete(GitHost):
    def create_mr(self, source, target, title):
        raise NotImplementedError

    def get_mr(self, number):
        raise NotImplementedError

    def auth_headers(self):
        return {"X-Test": self.token}


def test_request_builds_url_and_headers():
    sess = _Session(body={"ok": 1})
    host = _Concrete("http://h", "grp/demo", FAKE, session=sess)
    assert host._request("GET", "/x") == {"ok": 1}
    method, url, kwargs = sess.calls[0]
    assert url == "http://h/x"
    assert kwargs["headers"]["X-Test"] == FAKE


def test_http_error_message_omits_token():
    sess = _Session(status=401, body={"message": "unauthorized"})
    host = _Concrete("http://h", "grp/demo", FAKE, session=sess)
    with pytest.raises(HostError) as exc:
        host._request("POST", "/merge_requests", json={"title": "x"})
    assert exc.value.status == 401
    assert FAKE not in str(exc.value)


def test_network_error_does_not_leak_token():
    import requests

    sess = _Session(raise_exc=requests.ConnectionError(f"failed token={FAKE}"))
    host = _Concrete("http://h", "grp/demo", FAKE, session=sess)
    with pytest.raises(HostError) as exc:
        host._request("GET", "/x")
    assert FAKE not in str(exc.value)


def test_redact_replaces_token():
    host = _Concrete("http://h", "grp/demo", FAKE, session=_Session())
    assert host._redact(f"a {FAKE} b") == "a *** b"
