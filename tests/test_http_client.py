import pytest
import requests

from runtime.http_client import HttpClient, HttpClientError


class _Resp:
    def __init__(self, data, status=200):
        self._data = data
        self.status_code = status

    def json(self):
        return self._data


def test_joins_base_url_and_path(monkeypatch):
    calls = []
    monkeypatch.setattr(
        requests.Session, "request",
        lambda self, m, url, **kw: calls.append((m, url)) or _Resp({"ok": 1}),
    )
    c = HttpClient("http://h/api")
    assert c.request("POST", "/x") == {"ok": 1}
    assert calls == [("POST", "http://h/api/x")]


def test_retries_twice_on_connection_error(monkeypatch):
    n = {"i": 0}

    def boom(self, m, url, **kw):
        n["i"] += 1
        raise requests.ConnectionError("reset")

    monkeypatch.setattr(requests.Session, "request", boom)
    with pytest.raises(HttpClientError):
        HttpClient("http://h", retries=2).request("GET", "/x")
    assert n["i"] == 3


def test_does_not_retry_on_4xx(monkeypatch):
    n = {"i": 0}

    def not_found(self, m, url, **kw):
        n["i"] += 1
        return _Resp({}, status=404)

    monkeypatch.setattr(requests.Session, "request", not_found)
    with pytest.raises(HttpClientError, match="404"):
        HttpClient("http://h", retries=2).request("GET", "/x")
    assert n["i"] == 1


def test_does_not_retry_write_on_timeout(monkeypatch):
    n = {"i": 0}

    def slow(self, m, url, **kw):
        n["i"] += 1
        raise requests.Timeout("slow")

    monkeypatch.setattr(requests.Session, "request", slow)
    with pytest.raises(HttpClientError):
        HttpClient("http://h", retries=2).request("POST", "/x")
    assert n["i"] == 1


def test_still_retries_read_on_timeout(monkeypatch):
    n = {"i": 0}

    def slow(self, m, url, **kw):
        n["i"] += 1
        raise requests.Timeout("slow")

    monkeypatch.setattr(requests.Session, "request", slow)
    with pytest.raises(HttpClientError):
        HttpClient("http://h", retries=2).request("GET", "/x")
    assert n["i"] == 3
