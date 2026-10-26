"""本地数据目录与 .env 解析。"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml


class ConfigError(Exception):
    pass


_VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def substitute(value: Any, env: dict[str, str]) -> Any:
    if isinstance(value, str):
        def repl(match: re.Match[str]) -> str:
            key = match.group(1)
            if key not in env:
                raise ConfigError(f"未定义变量 {key}")
            return env[key]

        return _VAR.sub(repl, value)
    if isinstance(value, dict):
        return {k: substitute(v, env) for k, v in value.items()}
    if isinstance(value, list):
        return [substitute(v, env) for v in value]
    return value


def data_home() -> Path:
    env = os.getenv("DATA_TOOLS_HOME")
    return Path(env) if env else Path.home() / ".data-tools"


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
