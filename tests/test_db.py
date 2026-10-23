import psycopg
import pytest

from runtime.db import DbError, connect, execute


class _Cursor:
    description = ("col",)

    def __init__(self, rows, rowcount):
        self._rows = rows
        self.rowcount = rowcount

    def execute(self, sql, params=None):
        self.executed = (sql, params)

    def fetchall(self):
        return self._rows

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeConn:
    def __init__(self, rows, rowcount):
        self._rows = rows
        self._rowcount = rowcount

    def cursor(self):
        return _Cursor(self._rows, self._rowcount)


def test_missing_prefix_key_raises():
    with pytest.raises(DbError, match="DEV_HOST"):
        connect({"DEV_PORT": "5432"}, "DEV", "hexin_wms")


def test_connect_uses_prefixed_keys(monkeypatch):
    seen = {}
    monkeypatch.setattr(psycopg, "connect", lambda **kw: seen.update(kw) or object())
    env = {"DEV_HOST": "h", "DEV_PORT": "5432", "DEV_USER": "u", "DEV_PASSWORD": "p"}
    connect(env, "DEV", "db1")
    assert seen["host"] == "h"
    assert seen["port"] == 5432
    assert seen["user"] == "u"
    assert seen["password"] == "p"
    assert seen["dbname"] == "db1"
    assert seen["connect_timeout"] == 10


def test_execute_returns_rows_and_rowcount():
    conn = _FakeConn(rows=[("A",)], rowcount=3)
    rows, count = execute(conn, "update t set s=%s", ("A",))
    assert rows == [("A",)] and count == 3
