import pytest

from runtime.report_config import ReportConfigError, load_report_config, match_project


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_TOOLS_HOME", str(tmp_path))
    proj = tmp_path / "projects" / "demo"
    proj.mkdir(parents=True)
    (proj / ".env").write_text("ZENTAO_URL=http://z\nZENTAO_ACCOUNT=me\n", encoding="utf-8")
    (proj / "report.yaml").write_text(
        """git:
  repos: [C:/project/demo]
  authors: [me@example.com]
zentao:
  api: auto
  base_url: ${ZENTAO_URL}
  account: ${ZENTAO_ACCOUNT}
  product_id: 31
  project_ids: [73]
""",
        encoding="utf-8",
    )
    return proj


def test_loads_and_substitutes(project):
    cfg = load_report_config("demo")
    assert cfg.git.repos[0].name == "demo"
    assert cfg.zentao.base_url == "http://z"
    assert cfg.zentao.product_id == 31
    assert cfg.zentao.project_ids == [73]


def test_missing_file_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_TOOLS_HOME", str(tmp_path))
    (tmp_path / "projects" / "demo").mkdir(parents=True)
    with pytest.raises(ReportConfigError, match="未找到报告配置"):
        load_report_config("demo")


def test_unknown_api_version_raises(project):
    p = project / "report.yaml"
    p.write_text(p.read_text(encoding="utf-8").replace("api: auto", "api: v9"), encoding="utf-8")
    with pytest.raises(ReportConfigError, match="v9"):
        load_report_config("demo")


def test_no_source_raises(project):
    (project / "report.yaml").write_text("git:\n  repos: []\n  authors: []\n", encoding="utf-8")
    with pytest.raises(ReportConfigError, match="数据源"):
        load_report_config("demo")


def test_match_project_by_cwd(tmp_path):
    repo = tmp_path / "gitrepo"
    repo.mkdir()
    proj = tmp_path / "projects" / "demo"
    proj.mkdir(parents=True)
    (proj / "report.yaml").write_text(
        f"git:\n  repos: [{repo.as_posix()}]\n  authors: [me@x.com]\n", encoding="utf-8"
    )
    assert match_project(repo / "src", tmp_path) == "demo"
    assert match_project(tmp_path, tmp_path) is None


def test_match_project_returns_none_when_ambiguous(tmp_path):
    for pid in ("one", "two"):
        proj = tmp_path / "projects" / pid
        proj.mkdir(parents=True)
        (proj / "report.yaml").write_text(
            f"git:\n  repos: [{tmp_path.as_posix()}]\n  authors: [me@x.com]\n", encoding="utf-8"
        )
    assert match_project(tmp_path / "sub", tmp_path) is None
