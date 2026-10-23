import pytest

from runtime.auth import AuthError, build_auth


def test_none_type_returns_none():
    assert build_auth({"type": "none"}, None) is None
    assert build_auth(None, None) is None


def test_custom_impl_is_loaded(tmp_path):
    (tmp_path / "auth_impl.py").write_text(
        "class A:\n"
        "    def apply(self, headers):\n"
        "        return {**headers, 'X': '1'}\n"
        "def build():\n"
        "    return A()\n",
        encoding="utf-8",
    )
    auth = build_auth({"type": "custom", "impl": "auth_impl.py:build"}, tmp_path)
    assert auth.apply({}) == {"X": "1"}


def test_custom_without_impl_raises():
    with pytest.raises(AuthError):
        build_auth({"type": "custom"}, None)
