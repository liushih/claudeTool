"""本地数据目录与 .env 解析。"""

from __future__ import annotations

import os
from pathlib import Path

import yaml


class ConfigError(Exception):
    pass


def data_home() -> Path:
    env = os.getenv("HEXIN_DATA_HOME")
    return Path(env) if env else Path.home() / ".hexin-tools"


def project_dir(project_id: str) -> Path:
    return data_home() / "projects" / project_id


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        values[key.strip()] = val.strip()
    return values


def resolve_project(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    cfg = data_home() / "config.yaml"
    if cfg.exists():
        data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
        default = data.get("default_project")
        if default:
            return str(default)
    raise ConfigError("未指定项目：传入 project_id，或在 config.yaml 设置 default_project")
