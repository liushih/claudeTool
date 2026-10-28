"""项目级的 git 托管配置与令牌读取。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from runtime import config

HOST_KINDS = ("github", "gitee", "gitlab")


class GitHostConfigError(Exception):
    pass


@dataclass
class GitHostConfig:
    user_tag: str
    repo_path: Path
    kind: str
    base_url: str
    project_path: str
    token_key: str
    branches: dict[str, str] = field(default_factory=dict)
    forbid_commit_paths: list[str] = field(default_factory=list)


def _base(project_id: str, home: Path | None) -> Path:
    return (Path(home) / "projects" / project_id) if home is not None else config.project_dir(project_id)


def load_git_host_config(project_id: str, home: Path | None = None) -> GitHostConfig:
    path = _base(project_id, home) / "git_hosts.yaml"
    if not path.exists():
        raise GitHostConfigError(f"未找到 git_hosts.yaml：{path}")

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    host = data.get("host") or {}
    kind = str(host.get("kind") or "")
    if kind not in HOST_KINDS:
        raise GitHostConfigError(f"不支持的托管平台 {kind!r}，可选：{', '.join(HOST_KINDS)}")

    rules = data.get("rules") or {}
    return GitHostConfig(
        user_tag=str(data.get("user_tag") or ""),
        repo_path=Path(str(data.get("repo_path") or "")),
        kind=kind,
        base_url=str(host.get("base_url") or ""),
        project_path=str(host.get("project_path") or ""),
        token_key=str(host.get("token_key") or ""),
        branches={str(k): str(v) for k, v in (data.get("branches") or {}).items()},
        forbid_commit_paths=[str(p) for p in (rules.get("forbid_commit_paths") or [])],
    )


def read_token(project_id: str, token_key: str, home: Path | None = None) -> str:
    env = config.load_env(_base(project_id, home) / ".env")
    value = env.get(token_key, "")
    if not value:
        raise GitHostConfigError(f"缺少令牌 {token_key}，请在项目 .env 中填写")
    return value


def save_user_tag(project_id: str, user_tag: str, home: Path | None = None) -> None:
    path = _base(project_id, home) / "git_hosts.yaml"
    text = path.read_text(encoding="utf-8")
    updated, count = re.subn(r"^user_tag:.*$", f"user_tag: {user_tag}", text, count=1, flags=re.M)
    if count == 0:
        updated = f"user_tag: {user_tag}\n" + text
    path.write_text(updated, encoding="utf-8")
