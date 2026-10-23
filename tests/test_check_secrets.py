from scripts.check_secrets import main, scan


def test_flags_password_literal(tmp_path):
    f = tmp_path / "a.py"
    f.write_text('password = "SuperSecret123"\n', encoding="utf-8")
    hits = scan([f])
    assert hits and "password" in hits[0][2].lower()


def test_flags_private_ip(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("HOST = '192.168.1.10'\n", encoding="utf-8")
    assert scan([f])


def test_allows_env_reference(tmp_path):
    f = tmp_path / "a.py"
    f.write_text('password = os.getenv("PW")\n', encoding="utf-8")
    assert scan([f]) == []


def test_clean_tree_returns_zero(tmp_path):
    (tmp_path / "ok.py").write_text("x = 1\n", encoding="utf-8")
    assert main([str(tmp_path)]) == 0
