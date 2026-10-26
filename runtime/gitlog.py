"""按作者与日期采集 git 提交。"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

_SEP = "\x1f"


@dataclass
class Commit:
    hash: str
    date: str
    subject: str
    files: int


@dataclass
class RepoCommits:
    repo: str
    status: str
    commits: list[Commit] = field(default_factory=list)


def collect_git(repos: list[Path], authors: list[str], start: date, end: date) -> list[RepoCommits]:
    return [_collect_one(Path(repo), authors, start, end) for repo in repos]


def _collect_one(repo: Path, authors: list[str], start: date, end: date) -> RepoCommits:
    if not repo.is_dir():
        return RepoCommits(str(repo), f"missing: {repo}")

    cmd = [
        "git", "-C", str(repo), "log", "--no-merges", "--date=short",
        f"--pretty=format:%H{_SEP}%ad{_SEP}%s", "--name-only",
        f"--since={start} 00:00:00", f"--until={end} 23:59:59",
    ]
    cmd.extend(f"--author={author}" for author in authors)

    result = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if result.returncode != 0:
        lines = [line for line in result.stderr.strip().splitlines() if line.strip()]
        return RepoCommits(str(repo), f"error: {lines[-1] if lines else '未知错误'}")

    return RepoCommits(str(repo), "ok", _parse(result.stdout))


def _parse(text: str) -> list[Commit]:
    commits: list[Commit] = []
    current: Commit | None = None
    for line in text.splitlines():
        if _SEP in line:
            hash_, when, subject = line.split(_SEP, 2)
            current = Commit(hash=hash_.strip(), date=when.strip(), subject=subject.strip(), files=0)
            commits.append(current)
        elif line.strip() and current is not None:
            current.files += 1
    return commits
