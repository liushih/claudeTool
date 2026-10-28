import pytest

from runtime.git_host.base import HostError, MergeRequest
from runtime.git_host.rules import RuleViolation
from scripts.git_host import main


class _FakeRepo:
    def __init__(self):
        self.calls = []
        self.bring_in = []
        self.report = None

    def commit(self, message, forbidden):
        self.calls.append(("commit", message))
        return "abc1234"

    def push(self, branch):
        self.calls.append(("push", branch))

    def bring_in_commits(self, source, target, base):
        return list(self.bring_in)

    def merge(self, source, target, source_base, forbidden_targets, confirm_bring_in=False):
        self.calls.append(("merge", source, target, confirm_bring_in))
        if self.bring_in and target == "dev" and not confirm_bring_in:
            raise RuleViolation("net-increment", f"将带入 {len(self.bring_in)} 个提交")

    def create_branch(self, name, target):
        self.calls.append(("create_branch", name, target))

    def verify_flow(self, prod_branch, test_branch, target):
        self.calls.append(("verify_flow", prod_branch, test_branch, target))
        return self.report

    def hotfix_commits(self, fix_branch, prod_ref="origin/prod"):
        self.calls.append(("hotfix_commits", fix_branch))
        return ["h1", "h2"]

    def cherry_pick(self, commits):
        self.calls.append(("cherry_pick", list(commits)))
        return ["s1", "s2"]


class _FakeHost:
    def create_mr(self, source, target, title):
        return MergeRequest(number="1819", url="http://g/mr/1819", state="opened", mergeable=True)

    def get_mr(self, number):
        return MergeRequest(number=number, url="http://g/mr/" + number, state="merged", mergeable=None)


def _run(args, repo, host=None, capsys=None):
    return main(
        ["--project", "demo", *args],
        repo_fn=lambda *a, **k: repo,
        host_fn=lambda *a, **k: host or _FakeHost(),
    )


@pytest.fixture(autouse=True)
def project_config(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_TOOLS_HOME", str(tmp_path))
    proj = tmp_path / "projects" / "demo"
    proj.mkdir(parents=True)
    (proj / "git_hosts.yaml").write_text(
        "user_tag: lsh\n"
        "repo_path: C:/x\n"
        "host:\n"
        "  kind: gitlab\n"
        "  base_url: http://g\n"
        "  project_path: a/b\n"
        "  token_key: TOKEN_KEY\n"
        "branches: {dev: dev, test: test, prod: prod}\n"
        "rules:\n"
        "  forbid_commit_paths: [pom.xml]\n",
        encoding="utf-8",
    )
    (proj / ".env").write_text("TOKEN_KEY=fake-x\n", encoding="utf-8")
    return proj


@pytest.fixture
def repo():
    return _FakeRepo()


def test_commit_subcommand_calls_repo(repo, capsys):
    assert _run(["commit", "-m", "feat-1: x\n\ny"], repo) == 0
    assert repo.calls == [("commit", "feat-1: x\n\ny")]


def test_push_subcommand_calls_repo(repo, capsys):
    assert _run(["push", "--branch", "feature/dev/lsh/1-x"], repo) == 0
    assert ("push", "feature/dev/lsh/1-x") in repo.calls


def test_merge_to_test_is_rejected_with_rule_name(repo, capsys):
    rc = _run(["merge", "--from", "feature/dev/lsh/1-x", "--to", "test"], repo)
    assert rc == 1
    assert "[direct-merge]" in capsys.readouterr().out


def test_merge_with_bring_in_needs_confirmation(repo, capsys):
    repo.bring_in = ["abc1234"]
    args = ["merge", "--from", "feature/test/lsh/1-x", "--to", "dev"]
    assert _run(args, repo) == 1
    assert "net-increment" in capsys.readouterr().out
    assert _run(args + ["--confirm-bring-in"], repo) == 0


def test_mr_create_prints_url(repo, capsys):
    rc = _run(["mr", "create", "--from", "feature/test/lsh/1-x", "--to", "test", "--title", "t"], repo)
    assert rc == 0
    assert "http://g/mr/1819" in capsys.readouterr().out


def test_mr_status_prints_state(repo, capsys):
    rc = _run(["mr", "status", "1819"], repo)
    assert rc == 0
    assert "merged" in capsys.readouterr().out


def test_platform_error_exits_one_with_status(repo, capsys):
    class _Failing(_FakeHost):
        def create_mr(self, *a):
            raise HostError("POST /x 失败（HTTP 403）", status=403)
    rc = _run(["mr", "create", "--from", "feature/test/lsh/1-x", "--to", "test", "--title", "t"], repo, host=_Failing())
    assert rc == 1
    assert "403" in capsys.readouterr().out


def test_branch_create_calls_repo(repo, capsys):
    rc = _run(["branch", "create", "--name", "feature/dev/lsh/1-x", "--target", "dev"], repo)
    assert rc == 0
    assert ("create_branch", "feature/dev/lsh/1-x", "dev") in repo.calls


def test_verify_flow_is_read_only_and_prints(repo, capsys):
    from runtime.git_host.repo import FlowReport

    repo.report = FlowReport()
    rc = _run(["verify-flow", "--prod-branch", "prod", "--test-branch", "test", "--target", "dev"], repo)
    assert rc == 0
    assert ("verify_flow", "prod", "test", "dev") in repo.calls
    assert not any(call[0] in ("merge", "push", "commit") for call in repo.calls)


def test_hotfix_sync_cherry_picks_all_fix_commits(repo, capsys):
    rc = _run(["hotfix", "sync", "--fix-branch", "feature/prod/lsh/1-hot", "--task", "1"], repo)
    assert rc == 0
    assert ("hotfix_commits", "feature/prod/lsh/1-hot") in repo.calls
    assert ("cherry_pick", ["h1", "h2"]) in repo.calls
    assert not any(call[0] == "merge" for call in repo.calls)


def test_set_user_tag_persists(project_config, capsys):
    (project_config / "git_hosts.yaml").write_text(
        (project_config / "git_hosts.yaml").read_text(encoding="utf-8").replace("user_tag: lsh", "user_tag:"),
        encoding="utf-8",
    )
    assert main(["--project", "demo", "set-user-tag", "zhang"]) == 0
    assert "user_tag: zhang" in (project_config / "git_hosts.yaml").read_text(encoding="utf-8")


def test_set_user_tag_refuses_to_overwrite(project_config, capsys):
    assert main(["--project", "demo", "set-user-tag", "zhang"]) == 2
    assert "user_tag: lsh" in (project_config / "git_hosts.yaml").read_text(encoding="utf-8")
