import pytest

from runtime import config


def test_data_home_prefers_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_TOOLS_HOME", str(tmp_path))
    assert config.data_home() == tmp_path


def test_load_env_keeps_equals_and_hash(tmp_path):
    p = tmp_path / ".env"
    p.write_text("PW=a=b#c\n", encoding="utf-8")
    assert config.load_env(p)["PW"] == "a=b#c"


def test_resolve_project_explicit_beats_config(monkeypatch, tmp_path):
    (tmp_path / "config.yaml").write_text("default_project: from_config\n", encoding="utf-8")
    monkeypatch.setenv("DATA_TOOLS_HOME", str(tmp_path))
    assert config.resolve_project("explicit") == "explicit"


def test_resolve_project_falls_back_to_config(monkeypatch, tmp_path):
    (tmp_path / "config.yaml").write_text("default_project: from_config\n", encoding="utf-8")
    monkeypatch.setenv("DATA_TOOLS_HOME", str(tmp_path))
    assert config.resolve_project(None) == "from_config"


def test_resolve_project_without_any_source_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_TOOLS_HOME", str(tmp_path))
    with pytest.raises(config.ConfigError):
        config.resolve_project(None)


def test_substitute_keeps_nested_structure():
    assert config.substitute({"a": ["${N}"]}, {"N": "5"}) == {"a": ["5"]}


def test_substitute_reports_missing_var():
    with pytest.raises(config.ConfigError, match="NOPE"):
        config.substitute("${NOPE}", {})
