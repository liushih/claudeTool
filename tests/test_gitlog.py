import os
import subprocess
from datetime import date
from pathlib import Path

from runtime.gitlog import collect_git


def _commit(repo: Path, name: str, email: str, when: str, message: str, filename: str):
    (repo / filename).write_text(message, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", filename], check=True)
    env = {
        "GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email,
        "GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": email,
        "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when,
    }
    subprocess.run(["git", "-C", str(repo), "commit", "-m", message], check=True,
                   env={**os.environ, **env})


def _repo(tmp_path, name="demo"):
    repo = tmp_path / name
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    return repo


def test_filters_by_author_and_date(tmp_path):
    repo = _repo(tmp_path)
    _commit(repo, "me", "me@x.com", "2026-09-01T10:00:00", "feat: 旧", "b.txt")
    _commit(repo, "me", "me@x.com", "2026-10-21T10:00:00", "feat: 一", "a.txt")
    _commit(repo, "other", "o@x.com", "2026-10-22T10:00:00", "feat: 别人", "c.txt")

    out = collect_git([repo], ["me@x.com"], date(2026, 10, 19), date(2026, 10, 25))
    assert len(out) == 1 and out[0].status == "ok"
    assert [c.subject for c in out[0].commits] == ["feat: 一"]
    assert out[0].commits[0].files == 1


def test_missing_repo_is_recorded_not_raised(tmp_path):
    out = collect_git([tmp_path / "nope"], ["me@x.com"], date(2026, 10, 19), date(2026, 10, 25))
    assert out[0].status.startswith("missing")
    assert out[0].commits == []


def test_empty_range_returns_no_commits(tmp_path):
    repo = _repo(tmp_path)
    _commit(repo, "me", "me@x.com", "2026-10-21T10:00:00", "feat: 一", "a.txt")
    out = collect_git([repo], ["me@x.com"], date(2026, 11, 1), date(2026, 11, 7))
    assert out[0].commits == []
