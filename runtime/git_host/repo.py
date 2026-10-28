"""本地 git 操作封装。所有规则判断先于 git 写操作，失败时不改动仓库。"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .rules import RuleViolation, check_commit_message, check_commit_paths, check_merge

PROTECTED_BRANCHES = ("test", "dev", "prod")
PUSH_FORBIDDEN_LOCAL = ("test", "dev", "prod")


class RepoError(Exception):
    pass


@dataclass
class Commit:
    hash: str
    subject: str
    files: int = 0


@dataclass
class FlowReport:
    prod_into_test: list[Commit] = field(default_factory=list)
    test_net_vs_test: list[Commit] = field(default_factory=list)
    test_net_vs_target: list[Commit] = field(default_factory=list)
    prod_only: list[str] = field(default_factory=list)

    @property
    def safe(self) -> bool:
        return not self.prod_only


class Repo:
    def __init__(self, path: Path):
        self.path = Path(path)

    def _git(self, *args: str, check: bool = True) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.path), *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if check and result.returncode != 0:
            detail = (result.stderr or result.stdout).strip().splitlines()
            raise RepoError(detail[-1] if detail else f"git {args[0]} 失败")
        return result.stdout.strip()

    def current_branch(self) -> str:
        return self._git("rev-parse", "--abbrev-ref", "HEAD")

    def is_clean(self) -> bool:
        return self._git("status", "--porcelain") == ""

    def staged_paths(self) -> list[str]:
        out = self._git("diff", "--cached", "--name-only")
        return [line for line in out.splitlines() if line.strip()]

    def commit(self, message: str, forbidden: list[str]) -> str:
        check_commit_message(message)
        check_commit_paths(self.staged_paths(), forbidden)
        self._git("commit", "-q", "-m", message)
        return self._git("rev-parse", "--short", "HEAD")

    def _rev_list(self, spec: str) -> list[str]:
        out = self._git("rev-list", "--cherry-pick", "--right-only", spec, check=False)
        return [line for line in out.splitlines() if line.strip()]

    def _ref(self, branch: str) -> str | None:
        for candidate in (f"origin/{branch}", branch):
            if self._git("rev-parse", "--verify", "-q", candidate, check=False):
                return candidate
        return None

    def fork_base(self, source: str) -> str | None:
        best: tuple[int, str] | None = None
        for base in PROTECTED_BRANCHES:
            if base == source:
                continue
            ref = self._ref(base)
            if ref is None:
                continue
            count = self._git("rev-list", "--count", f"{ref}..{source}", check=False)
            if not count.isdigit():
                continue
            if best is None or int(count) < best[0]:
                best = (int(count), base)
        return best[1] if best else None

    def bring_in_commits(self, source: str, target: str, base: str) -> list[str]:
        ordered = self._rev_list(f"{target}...{source}")
        own = set(self._rev_list(f"{base}...{source}"))
        return [h for h in ordered if h not in own]

    def merge(
        self,
        source: str,
        target: str,
        source_base: str | None,
        forbidden_targets: list[str],
        confirm_bring_in: bool = False,
    ) -> None:
        base = source_base or self.fork_base(source) or target
        bring_in = self.bring_in_commits(source, target, base) if target == "dev" else []
        pending = check_merge(source, target, source_base, bring_in)
        if pending and not confirm_bring_in:
            raise RuleViolation(
                "net-increment",
                f"将带入 {target} 的非本分支内容 {len(pending)} 个提交，确认后请加 --confirm-bring-in",
            )
        self._git("checkout", "-q", target)
        result = subprocess.run(
            ["git", "-C", str(self.path), "merge", "--no-ff", "-q", source],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if result.returncode != 0:
            conflicts = self._git("diff", "--name-only", "--diff-filter=U", check=False)
            self._git("merge", "--abort", check=False)
            files = ", ".join(line for line in conflicts.splitlines() if line.strip()) or "未知文件"
            raise RepoError(f"合并冲突，已中止。冲突文件：{files}")

    def push(self, branch: str) -> None:
        if branch in PUSH_FORBIDDEN_LOCAL:
            raise RuleViolation(
                "push-target",
                f"本地分支名为 {branch} 时不允许推送，请使用 feature/<目标>/<用户标识>/<任务号>-<描述>",
            )
        self._git("push", "-u", "origin", f"{branch}:{branch}")

    def create_branch(self, name: str, target: str) -> None:
        self._git("fetch", "-q", "origin")
        self._git("checkout", "-q", "-b", name, "--no-track", f"origin/{target}")
        ahead = self._git("rev-list", "--count", f"origin/{target}..HEAD")
        if ahead != "0":
            raise RepoError(f"新分支起点与 origin/{target} 不一致（领先 {ahead} 个提交）")

    def hotfix_commits(self, fix_branch: str, prod_ref: str = "origin/prod") -> list[str]:
        commits = self._rev_list(f"{prod_ref}...{fix_branch}")
        commits = list(reversed(commits))
        if not commits:
            raise RepoError("热修复分支相对 prod 无新提交")
        return commits

    def cherry_pick(self, commits: list[str]) -> list[str]:
        created: list[str] = []
        for commit in commits:
            result = subprocess.run(
                ["git", "-C", str(self.path), "cherry-pick", "-x", commit],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            if result.returncode != 0:
                conflicts = self._git("diff", "--name-only", "--diff-filter=U", check=False)
                self._git("cherry-pick", "--abort", check=False)
                files = ", ".join(line for line in conflicts.splitlines() if line.strip()) or "未知文件"
                raise RepoError(f"cherry-pick 冲突，已中止。冲突文件：{files}")
            created.append(self._git("rev-parse", "--short", "HEAD"))
        return created

    def check_prod_derived(self, source_base: str | None, target_branch: str) -> None:
        if source_base == "prod" and target_branch in ("dev", "test"):
            raise RuleViolation(
                "prod-derived",
                f"prod 衍生分支不能直接合并到 {target_branch}，请先经过 test 衍生的同步分支",
            )

    def verify_flow(self, prod_branch: str, test_branch: str, target: str) -> FlowReport:
        report = FlowReport()
        report.prod_into_test = self._commits(f"origin/{test_branch}...{prod_branch}")
        report.test_net_vs_test = self._commits(f"origin/{test_branch}...{test_branch}")
        report.test_net_vs_target = self._commits(f"origin/{target}...{test_branch}")
        prod_only = self._rev_list(f"origin/{test_branch}...origin/{prod_branch}")
        report.prod_only = prod_only
        return report

    def _commits(self, spec: str) -> list[Commit]:
        hashes = self._rev_list(spec)
        out: list[Commit] = []
        for h in hashes:
            subject = self._git("log", "-1", "--format=%s", h, check=False)
            files = self._git("diff-tree", "--no-commit-id", "--name-only", "-r", h, check=False)
            out.append(Commit(hash=h, subject=subject, files=len([f for f in files.splitlines() if f.strip()])))
        return out
