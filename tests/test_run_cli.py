import pytest

from scripts.run import main


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("HEXIN_DATA_HOME", str(tmp_path))
    proj = tmp_path / "projects" / "demo"
    proj.mkdir(parents=True)
    (proj / ".env").write_text("BASE=http://example\n", encoding="utf-8")
    (proj / "hook.py").write_text(
        "def go(ctx, resp):\n    return {'ok': True}\n", encoding="utf-8"
    )
    (proj / "adapter.yaml").write_text(
        """version: 1
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
    steps:
      - id: hook
        impl: hook.py:go
pitfalls: []
""",
        encoding="utf-8",
    )
    return proj


def test_runs_entity_and_writes_ledger(project, capsys):
    rc = main(
        ["--project", "demo", "--entity", "order", "--count", "1", "--workers", "1", "--run-id", "r"],
        client_factory=lambda: object(),
    )
    assert rc == 0
    lines = (project / "ledger.csv").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert ",done" in lines[1]


def test_unknown_entity_returns_error(project):
    with pytest.raises(SystemExit):
        main(["--project", "demo", "--entity", "nope"], client_factory=lambda: object())
