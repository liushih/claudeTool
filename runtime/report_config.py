"""加载报告采集配置，并按工作目录定位项目。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import config

API_VERSIONS = {"auto", "v1", "v2"}


class ReportConfigError(Exception):
    pass


@dataclass
class GitConfig:
    repos: list[Path] = field(default_factory=list)
    authors: list[str] = field(default_factory=list)


@dataclass
class ZentaoConfig:
    api: str = "auto"
    base_url: str = ""
    account: str = ""
    password: str = ""
    product_id: int | None = None
    project_ids: list[int] = field(default_factory=list)


@dataclass
class ReportConfig:
    git: GitConfig = field(default_factory=GitConfig)
    zentao: ZentaoConfig = field(default_factory=ZentaoConfig)


def load_report_config(project_id: str, home: Path | None = None) -> ReportConfig:
    base = (Path(home) / "projects" / project_id) if home is not None else config.project_dir(project_id)
    path = base / "report.yaml"
    if not path.exists():
        raise ReportConfigError(f"未找到报告配置：{path}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    try:
        data = config.substitute(raw, config.load_env(base / ".env"))
    except config.ConfigError as exc:
        raise ReportConfigError(str(exc)) from exc

    git_raw = data.get("git") or {}
    zentao_raw = data.get("zentao") or {}

    api = str(zentao_raw.get("api") or "auto")
    if api not in API_VERSIONS:
        raise ReportConfigError(f"不支持的禅道 API 版本：{api}")

    git = GitConfig(
        repos=[Path(str(item)) for item in (git_raw.get("repos") or [])],
        authors=[str(item) for item in (git_raw.get("authors") or [])],
    )
    zentao = ZentaoConfig(
        api=api,
        base_url=str(zentao_raw.get("base_url") or ""),
        account=str(zentao_raw.get("account") or ""),
        password=str(zentao_raw.get("password") or ""),
        product_id=_as_int(zentao_raw.get("product_id")),
        project_ids=[_as_int(item) for item in (zentao_raw.get("project_ids") or []) if _as_int(item) is not None],
    )

    if not git.repos and not zentao.base_url:
        raise ReportConfigError("report.yaml 未配置任何数据源")

    return ReportConfig(git=git, zentao=zentao)


def match_project(cwd: Path, home: Path | None = None) -> str | None:
    root = Path(home) if home is not None else config.data_home()
    projects = root / "projects"
    if not projects.is_dir():
        return None

    current = Path(cwd).resolve()
    hits: set[str] = set()
    for entry in sorted(projects.iterdir()):
        if not (entry / "report.yaml").exists():
            continue
        try:
            cfg = load_report_config(entry.name, home=root)
        except (ReportConfigError, OSError, yaml.YAMLError):
            continue
        for repo in cfg.git.repos:
            target = repo.resolve()
            if current == target or target in current.parents:
                hits.add(entry.name)
                break

    return hits.pop() if len(hits) == 1 else None


def _as_int(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
