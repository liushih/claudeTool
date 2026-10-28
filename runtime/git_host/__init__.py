"""托管平台适配器的选择与构造。"""

from __future__ import annotations

from pathlib import Path

from .base import GitHost
from .config import load_git_host_config, read_token
from .gitee import GiteeHost
from .github import GitHubHost
from .gitlab import GitLabHost

DEFAULT_BASE_URL = {
    "github": "https://api.github.com",
    "gitee": "https://gitee.com",
}

_HOSTS = {
    "github": GitHubHost,
    "gitee": GiteeHost,
    "gitlab": GitLabHost,
}


def get_host(project_id: str, home: Path | None = None) -> GitHost:
    cfg = load_git_host_config(project_id, home=home)
    token = read_token(project_id, cfg.token_key, home=home)
    base_url = _base_url(cfg)
    return _HOSTS[cfg.kind](base_url, cfg.project_path, token)


def _base_url(cfg) -> str:
    return cfg.base_url or DEFAULT_BASE_URL.get(cfg.kind, "")
