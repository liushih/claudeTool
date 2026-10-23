from runtime.verify import run_verify


class _Cursor:
    def __init__(self, value):
        self._value = value

    def execute(self, sql, params=None):
        self.executed = (sql, params)

    def fetchone(self):
        return (self._value,)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeConn:
    def __init__(self, value):
        self._value = value

    def cursor(self):
        return _Cursor(self._value)


def test_returns_true_when_value_matches():
    ok, got = run_verify(
        _FakeConn("UPLOADED"),
        {"sql": "select status from t where no = %(no)s", "expect": "UPLOADED"},
        {"no": "X"},
    )
    assert ok is True and got == "UPLOADED"


def test_returns_false_on_mismatch():
    ok, got = run_verify(_FakeConn("NEW"), {"sql": "select status from t", "expect": "UPLOADED"}, {})
    assert ok is False and got == "NEW"


def test_empty_spec_is_pass():
    assert run_verify(_FakeConn("x"), None, {}) == (True, None)
