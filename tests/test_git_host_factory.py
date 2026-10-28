import pytest

from runtime.git_host import get_host
from runtime.git_host.config import GitHostConfigError
from runtime.git_host.github import GitHubHost
from runtime.git_host.gitee import GiteeHost
from runtime.git_host.gitlab import GitLabHost


def _project(home, kind, token_key="TOKEN_KEY", env_line="TOKEN_KEY=fake-x"):
    proj = home / "projects" / "demo"
    proj.mkdir(parents=True)
    (proj / "git_hosts.yaml").write_text(
        f"""user_tag: lsh
repo_path: C:/x
host:
  kind: {kind}
  base_url: http://h
  project_path: a/b
  token_key: {token_key}
branches: {{dev: dev, test: test, prod: prod}}
rules:
  forbid_commit_paths: []
""",
        encoding="utf-8",
    )
    (proj / ".env").write_text(env_line + "\n", encoding="utf-8")
    return home


@pytest.mark.parametrize("kind,cls", [("gitlab", GitLabHost), ("github", GitHubHost), ("gitee", GiteeHost)])
def test_factory_picks_class_by_kind(tmp_path, kind, cls):
    home = _project(tmp_path, kind)
    assert isinstance(get_host("demo", home=home), cls)


def test_factory_fails_when_token_missing(tmp_path):
    home = _project(tmp_path, "gitlab", token_key="MISSING_KEY", env_line="OTHER=1")
    with pytest.raises(GitHostConfigError, match="MISSING_KEY"):
        get_host("demo", home=home)


def test_github_default_base_url_when_unset(tmp_path):
    home = tmp_path
    proj = home / "projects" / "demo"
    proj.mkdir(parents=True)
    (proj / "git_hosts.yaml").write_text(
        "user_tag: lsh\nrepo_path: C:/x\nhost:\n  kind: github\n  project_path: a/b\n  token_key: TOKEN_KEY\n"
        "branches: {dev: dev}\nrules:\n  forbid_commit_paths: []\n",
        encoding="utf-8",
    )
    (proj / ".env").write_text("TOKEN_KEY=fake-x\n", encoding="utf-8")
    assert get_host("demo", home=home).base_url == "https://api.github.com"


def test_gitee_default_base_url_when_unset(tmp_path):
    home = tmp_path
    proj = home / "projects" / "demo"
    proj.mkdir(parents=True)
    (proj / "git_hosts.yaml").write_text(
        "user_tag: lsh\nrepo_path: C:/x\nhost:\n  kind: gitee\n  project_path: a/b\n  token_key: TOKEN_KEY\n"
        "branches: {dev: dev}\nrules:\n  forbid_commit_paths: []\n",
        encoding="utf-8",
    )
    (proj / ".env").write_text("TOKEN_KEY=fake-x\n", encoding="utf-8")
    assert get_host("demo", home=home).base_url == "https://gitee.com"
