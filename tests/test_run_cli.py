import subprocess
import sys
from pathlib import Path

import pytest

from scripts.run import main


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_TOOLS_HOME", str(tmp_path))
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
    database: hexin_wms
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


def test_cli_runs_outside_pytest(tmp_path):
    root = Path(__file__).resolve().parents[1]
    out = subprocess.run(
        [sys.executable, str(root / "scripts" / "run.py"), "--help"],
        cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert out.returncode == 0, out.stderr


class _Cursor:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        pass

    def fetchone(self):
        return ("NEW",)


class _Conn:
    def cursor(self):
        return _Cursor()

    def close(self):
        pass


def test_verify_mismatch_returns_nonzero(project, monkeypatch):
    text = (project / "adapter.yaml").read_text(encoding="utf-8").replace(
        "    stop_at: DONE\n",
        "    stop_at: DONE\n"
        "    verify:\n"
        '      sql: "select status from t where no = %(no)s"\n'
        "      expect: DONE\n",
    )
    (project / "adapter.yaml").write_text(text, encoding="utf-8")
    monkeypatch.setattr("scripts.run.db.connect", lambda *a, **k: _Conn())
    rc = main(
        ["--project", "demo", "--entity", "order", "--count", "1", "--workers", "1", "--run-id", "v"],
        client_factory=lambda: object(),
    )
    assert rc == 1
