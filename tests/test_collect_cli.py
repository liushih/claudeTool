import json

import pytest

from scripts.collect import main


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_TOOLS_HOME", str(tmp_path))
    proj = tmp_path / "projects" / "demo"
    proj.mkdir(parents=True)
    (proj / ".env").write_text("ZENTAO_URL=http://z\n", encoding="utf-8")
    (proj / "report.yaml").write_text(
        """git:
  repos: [C:/project/demo]
  authors: [me@x.com]
zentao:
  api: v2
  base_url: ${ZENTAO_URL}
  account: me
""",
        encoding="utf-8",
    )
    return tmp_path


def test_writes_json_with_sources(project, tmp_path):
    out = tmp_path / "out.json"
    rc = main(
        ["--project", "demo", "--type", "weekly", "--anchor", "2026-10-26", "--out", str(out)],
        git_fn=lambda repos, authors, start, end: [],
        zentao_fn=lambda cfg, start, end: ([], [], []),
    )
    assert rc == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["period"] == {"type": "weekly", "start": "2026-10-26", "end": "2026-11-01"}
    assert data["sources"] == {"git": "ok", "zentao": "ok"}
    assert data["project"] == "demo"


def test_partial_failure_is_recorded(project, tmp_path):
    out = tmp_path / "out.json"
    main(
        ["--project", "demo", "--type", "daily", "--anchor", "2026-10-26", "--out", str(out)],
        git_fn=lambda *a: [],
        zentao_fn=lambda *a: ([], [], ["禅道采集失败：401"]),
    )
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["sources"]["zentao"].startswith("failed")
    assert "401" in data["sources"]["zentao"]


def test_invalid_range_exits_nonzero(project, tmp_path):
    with pytest.raises(SystemExit):
        main(["--project", "demo", "--type", "review",
              "--start", "2026-09-30", "--end", "2026-07-01", "--out", str(tmp_path / "x.json")])
