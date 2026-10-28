"""git 托管的规则校验（纯函数，不调用 git 或平台 API）。"""

from __future__ import annotations

import re
from dataclasses import dataclass

_BRANCH = re.compile(r"^feature/(dev|test|prod)/([A-Za-z0-9_-]+)/(\d+)-([^\s/\\]+)$")
_COMMIT_HEAD = re.compile(r"^(feat|fix)-(\d+): \S.*$")


class RuleViolation(Exception):
    def __init__(self, rule: str, message: str):
        super().__init__(message)
        self.rule = rule
        self.message = message


@dataclass(frozen=True)
class BranchInfo:
    target: str
    user_tag: str
    task: str
    desc: str


def parse_branch(name: str) -> BranchInfo | None:
    match = _BRANCH.match(name)
    if not match:
        return None
    target, user_tag, task, desc = match.groups()
    return BranchInfo(target=target, user_tag=user_tag, task=task, desc=desc)


def check_branch_name(name: str, user_tag: str) -> None:
    info = parse_branch(name)
    if info is None:
        raise RuleViolation(
            "branch-naming",
            f"分支名 {name} 不符合 feature/<目标>/<用户标识>/<任务号>-<描述>",
        )
    if user_tag and info.user_tag != user_tag:
        raise RuleViolation(
            "branch-naming",
            f"分支名中的用户标识 {info.user_tag} 与配置的 {user_tag} 不一致",
        )


def check_commit_message(message: str) -> None:
    lines = message.strip().splitlines()
    if not lines or not _COMMIT_HEAD.match(lines[0]):
        raise RuleViolation(
            "commit-message",
            "提交信息首行须为 feat-<任务号>: <中文描述> 或 fix-<任务号>: <中文描述>",
        )
    if not any(line.strip() for line in lines[1:]):
        raise RuleViolation("commit-message", "提交信息必须包含正文，概述本次修改")


def check_commit_paths(paths: list[str], forbidden: list[str]) -> None:
    hits = [path for path in paths if path in forbidden]
    if hits:
        raise RuleViolation(
            "forbidden-path",
            f"本地环境配置不允许提交：{', '.join(hits)}",
        )


def check_merge(
    source: str,
    target: str,
    source_base: str | None,
    bring_in: list[str],
) -> list[str]:
    if target in ("test", "prod"):
        raise RuleViolation("direct-merge", f"{target} 只能通过 MR 合并，请使用 mr create --to {target}")
    if source_base == "prod" and target in ("dev", "test"):
        raise RuleViolation(
            "prod-derived",
            f"prod 衍生分支不能直接合并到 {target}，请先经过 test 衍生的同步分支",
        )
    if target == "dev" and bring_in:
        return list(bring_in)
    return []
