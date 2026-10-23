import pytest

from runtime import adapter

MINIMAL = """version: 1
project: demo
envs:
  dev:
    base_url: ${BASE}
    db_prefix: DEV
auth:
  type: none
entities:
  order:
    description: 测试单
    stop_at: DONE
    id_rule: "T{idx}"
    steps:
      - id: create
        call: POST /x
pitfalls: []
"""


def _write_adapter(tmp_path, body: str):
    proj = tmp_path / "projects" / "demo"
    proj.mkdir(parents=True)
    (proj / "adapter.yaml").write_text(body, encoding="utf-8")
    (proj / ".env").write_text("BASE=http://example\n", encoding="utf-8")
    return proj


def test_missing_var_raises(monkeypatch, tmp_path):
    _write_adapter(tmp_path, MINIMAL.replace("${BASE}", "${NOPE}"))
    monkeypatch.setenv("HEXIN_DATA_HOME", str(tmp_path))
    with pytest.raises(adapter.AdapterError, match="NOPE"):
        adapter.load_adapter("demo")


def test_step_with_two_modes_raises(monkeypatch, tmp_path):
    _write_adapter(
        tmp_path,
        MINIMAL.replace("        call: POST /x", "        call: POST /x\n        poll: GET /y"),
    )
    monkeypatch.setenv("HEXIN_DATA_HOME", str(tmp_path))
    with pytest.raises(adapter.AdapterError, match="exactly one"):
        adapter.load_adapter("demo")


def test_entity_without_steps_raises(monkeypatch, tmp_path):
    _write_adapter(tmp_path, MINIMAL.replace("      - id: create\n        call: POST /x\n", ""))
    monkeypatch.setenv("HEXIN_DATA_HOME", str(tmp_path))
    with pytest.raises(adapter.AdapterError, match="steps"):
        adapter.load_adapter("demo")


def test_loads_and_substitutes(monkeypatch, tmp_path):
    _write_adapter(tmp_path, MINIMAL)
    monkeypatch.setenv("HEXIN_DATA_HOME", str(tmp_path))
    a = adapter.load_adapter("demo")
    assert a.project == "demo"
    assert a.envs["dev"]["base_url"] == "http://example"


def test_unknown_before_target_raises(monkeypatch, tmp_path):
    _write_adapter(
        tmp_path,
        MINIMAL.replace("        call: POST /x", "        call: POST /x\n        before: [nope]"),
    )
    monkeypatch.setenv("HEXIN_DATA_HOME", str(tmp_path))
    with pytest.raises(adapter.AdapterError, match="nope"):
        adapter.load_adapter("demo")
