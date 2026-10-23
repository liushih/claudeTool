"""加载并校验本地 adapter.yaml。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import yaml

from . import config


class AdapterError(Exception):
    pass


@dataclass
class Step:
    id: str
    call: str | None = None
    poll: str | None = None
    until: str | None = None
    timeout: int = 60
    before: list[str] = field(default_factory=list)
    impl: str | None = None
    body: dict | None = None
    params: dict | None = None


@dataclass
class Entity:
    id: str
    description: str = ""
    stop_at: str | None = None
    id_rule: str = "{run_id}{idx:04d}"
    steps: list[Step] = field(default_factory=list)
    verify: dict | None = None


@dataclass
class Adapter:
    version: int
    project: str
    envs: dict[str, dict]
    auth: dict
    entities: dict[str, Entity]
    pitfalls: list[dict]


_VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _substitute(value: Any, env: dict[str, str]) -> Any:
    if isinstance(value, str):
        def repl(match: re.Match[str]) -> str:
            key = match.group(1)
            if key not in env:
                raise AdapterError(f"未定义变量 {key}")
            return env[key]

        return _VAR.sub(repl, value)
    if isinstance(value, dict):
        return {k: _substitute(v, env) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute(v, env) for v in value]
    return value


def load_adapter(project_id: str) -> Adapter:
    base = config.project_dir(project_id)
    path = base / "adapter.yaml"
    if not path.exists():
        raise AdapterError(f"未找到适配层：{path}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    version = raw.get("version")
    if version != 1:
        raise AdapterError(f"不支持的适配层版本：{version}")

    data = _substitute(raw, config.load_env(base / ".env"))
    entities: dict[str, Entity] = {}
    for eid, ent in (data.get("entities") or {}).items():
        steps_raw = ent.get("steps") or []
        if not steps_raw:
            raise AdapterError(f"实体 {eid} 缺少 steps")

        steps: list[Step] = []
        for s in steps_raw:
            sid = s.get("id")
            modes = [m for m in ("call", "poll", "impl") if s.get(m)]
            if len(modes) != 1:
                raise AdapterError(f"步骤 {sid} 需要 exactly one of call/poll/impl，当前为 {modes}")
            steps.append(Step(
                id=sid,
                call=s.get("call"),
                poll=s.get("poll"),
                until=s.get("until"),
                timeout=int(s.get("timeout", 60)),
                before=list(s.get("before") or []),
                impl=s.get("impl"),
                body=s.get("body"),
                params=s.get("params"),
            ))

        entities[eid] = Entity(
            id=eid,
            description=ent.get("description", ""),
            stop_at=ent.get("stop_at"),
            id_rule=ent.get("id_rule", "{run_id}{idx:04d}"),
            steps=steps,
            verify=ent.get("verify"),
        )

        step_ids = {s.id for s in steps}
        for s in steps:
            for pre in s.before:
                if pre not in step_ids:
                    raise AdapterError(f"步骤 {s.id} 依赖的步骤 {pre} 未在同实体 steps 中声明")

    if not entities:
        raise AdapterError("适配层没有定义任何 entities")

    return Adapter(
        version=1,
        project=data.get("project", project_id),
        envs=data.get("envs") or {},
        auth=data.get("auth") or {},
        entities=entities,
        pitfalls=data.get("pitfalls") or [],
    )
