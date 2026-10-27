"""按项目配置执行一条 Redis 命令。"""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from runtime.adapter import load_adapter  # noqa: E402
from runtime.redis_client import DESTRUCTIVE_COMMANDS, WRITE_COMMANDS, connect  # noqa: E402


def main(argv: list[str] | None = None, connect_fn=None) -> int:
    parser = argparse.ArgumentParser(description="按项目配置执行一条 Redis 命令")
    parser.add_argument("--project", required=True)
    parser.add_argument("--env", default="dev")
    parser.add_argument("--cmd", required=True, help='如 "GET user:1"')
    args = parser.parse_args(argv)

    adapter = load_adapter(args.project)
    env = adapter.envs.get(args.env)
    if not env:
        parser.error(f"未知环境 {args.env}")

    prefix = env.get("redis_prefix")
    if not prefix:
        parser.error(f"环境 {args.env} 未配置 redis_prefix")

    parts = shlex.split(args.cmd)
    if not parts:
        parser.error("--cmd 不能为空")

    client = (connect_fn or connect)(env, prefix)

    name = parts[0].upper()
    if name in WRITE_COMMANDS:
        print(f"[写] 环境={args.env} 前缀={prefix} 命令={' '.join(parts)}")
        if name in DESTRUCTIVE_COMMANDS:
            print("警示：该命令会清空数据，请确认影响范围")

    value, kind = client.command(parts)
    _print(value, kind)
    return 0


def _print(value, kind: str) -> None:
    if kind == "scan":
        print("\n".join(str(item) for item in value))
    elif kind == "hash":
        print(json.dumps(value, ensure_ascii=False, indent=2, default=str))
    elif value is None:
        print("(nil)")
    else:
        print(value)


if __name__ == "__main__":
    raise SystemExit(main())
