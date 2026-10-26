"""按项目配置执行一条 SQL。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from runtime import db  # noqa: E402
from runtime.adapter import load_adapter  # noqa: E402
from runtime.config import load_env, project_dir  # noqa: E402


def main(argv: list[str] | None = None, connect_fn=None) -> int:
    parser = argparse.ArgumentParser(description="按项目配置执行一条 SQL")
    parser.add_argument("--project", required=True)
    parser.add_argument("--env", default="dev")
    parser.add_argument("--sql", required=True)
    parser.add_argument("--param", action="append", default=[], metavar="KEY=VALUE")
    args = parser.parse_args(argv)

    adapter = load_adapter(args.project)
    env = adapter.envs.get(args.env)
    if not env:
        parser.error(f"未知环境 {args.env}")

    prefix = env.get("db_prefix")
    database = env.get("database")
    if not prefix or not database:
        parser.error(f"环境 {args.env} 缺少 db_prefix 或 database")

    params: dict[str, str] = {}
    for item in args.param:
        key, _, value = item.partition("=")
        params[key] = value

    connect = connect_fn or db.connect
    conn = connect(load_env(project_dir(args.project) / ".env"), prefix, database)
    try:
        rows, count = db.execute(conn, args.sql, params or None)
    finally:
        conn.close()

    for row in rows:
        print("\t".join("" if value is None else str(value) for value in row))
    print(f"{len(rows)} 行，影响 {count} 行")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
