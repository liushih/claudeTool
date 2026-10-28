import pytest

from scripts.install import install, remove

NAMES = ("data-gen-core", "db-access", "adapter-bootstrap", "report-writer", "git-workflow")


@pytest.fixture
def tools(tmp_path):
    root = tmp_path / "tools"
    for name in NAMES:
        d = root / "skills" / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {name} 测试\n---\n\n# {name}\n\n正文 <TOOLS_DIR>\n",
            encoding="utf-8",
        )
    return root


def test_claude_skill_has_name_and_description(tmp_path, tools):
    paths = install(["claude"], "global", None, tools, home=tmp_path)
    by_name = {p.parent.name: p for p in paths}
    text = by_name["data-gen-core"].read_text(encoding="utf-8")
    assert "name: data-gen-core" in text
    assert "description:" in text
    assert by_name["data-gen-core"].name == "SKILL.md"


def test_tools_dir_placeholder_is_replaced(tmp_path, tools):
    paths = install(["claude"], "global", None, tools, home=tmp_path)
    text = paths[0].read_text(encoding="utf-8")
    assert "<TOOLS_DIR>" not in text
    assert tools.as_posix() in text


def test_cursor_rule_has_always_apply(tmp_path, tools):
    repo = tmp_path / "repo"
    paths = install(["cursor"], "project", repo, tools, home=tmp_path)
    target = next(p for p in paths if p.stem == "data-gen-core")
    text = target.read_text(encoding="utf-8")
    assert "alwaysApply: false" in text
    assert target.suffix == ".mdc"


def test_codex_block_is_not_duplicated(tmp_path, tools):
    repo = tmp_path / "repo"
    install(["codex"], "project", repo, tools, home=tmp_path)
    install(["codex"], "project", repo, tools, home=tmp_path)
    text = (repo / "AGENTS.md").read_text(encoding="utf-8")
    assert text.count("data-tools:begin") == 1


def test_remove_deletes_generated(tmp_path, tools):
    repo = tmp_path / "repo"
    install(["cursor"], "project", repo, tools, home=tmp_path)
    remove(["cursor"], "project", repo, home=tmp_path)
    assert not (repo / ".cursor" / "rules" / "data-gen-core.mdc").exists()


def test_generated_claude_file_starts_with_frontmatter(tmp_path, tools):
    paths = install(["claude"], "global", None, tools, home=tmp_path)
    assert paths
    for path in paths:
        assert path.read_text(encoding="utf-8").startswith("---\n")


def test_generated_cursor_file_starts_with_frontmatter(tmp_path, tools):
    repo = tmp_path / "repo"
    paths = install(["cursor"], "project", repo, tools, home=tmp_path)
    assert paths
    for path in paths:
        assert path.read_text(encoding="utf-8").startswith("---\n")


def test_remove_without_project_dir_skips_project_tools(tmp_path, tools):
    install(["claude"], "global", None, tools, home=tmp_path)
    remove(["claude", "cursor", "codex"], "global", None, home=tmp_path)
    assert not (tmp_path / ".claude" / "skills" / "data-gen-core" / "SKILL.md").exists()
