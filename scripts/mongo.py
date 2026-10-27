"""按项目配置执行一次 MongoDB 查询。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from runtime.adapter import load_adapter  # noqa: E402
from runtime.mongo_client import WRITE_OPS, connect  # noqa: E402

OPERATIONS = ("find", "aggregate", "count", "insert", "update", "delete")


def main(argv: list[str] | None = None, connect_fn=None) -> int:
    parser = argparse.ArgumentParser(description="按项目配置执行一次 MongoDB 查询")
    parser.add_argument("--project", required=True)
    parser.add_argument("--env", default="dev")
    parser.add_argument("--collection", required=True)
    for op in OPERATIONS:
        parser.add_argument(f"--{op}", help="JSON 参数")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args(argv)

    chosen = [(op, getattr(args, op)) for op in OPERATIONS if getattr(args, op) is not None]
    if len(chosen) != 1:
        parser.error(f"需要且只能指定一个操作：{'/'.join('--' + op for op in OPERATIONS)}")
    op, raw = chosen[0]

    try:
        payload = json.loads(raw)
    except ValueError as exc:
        parser.error(f"{op} 参数不是合法 JSON：{exc}")

    adapter = load_adapter(args.project)
    env = adapter.envs.get(args.env)
    if not env:
        parser.error(f"未知环境 {args.env}")

    prefix = env.get("mongo_prefix")
    if not prefix:
        parser.error(f"环境 {args.env} 未配置 mongo_prefix")
    database = env.get("mongo_database")
    if not database:
        parser.error(f"环境 {args.env} 未配置 mongo_database")

    client = (connect_fn or connect)(env, prefix, database)

    if op in WRITE_OPS:
        print(f"[写] 环境={args.env} 库={database} 集合={args.collection} 操作={op}")
        if op == "delete" and isinstance(payload, dict) and payload.get("many") and not payload.get("filter"):
            print("警示：无条件删除整个集合，请确认影响范围")

    result = client.run(args.collection, op, payload, limit=args.limit)
    if op in ("find", "aggregate"):
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    elif op == "count":
        print(result)
    else:
        print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
