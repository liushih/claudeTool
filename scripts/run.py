"""按适配层批量造数的执行入口。"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime import db  # noqa: E402
from runtime.adapter import load_adapter  # noqa: E402
from runtime.auth import build_auth  # noqa: E402
from runtime.config import load_env, project_dir  # noqa: E402
from runtime.http_client import HttpClient  # noqa: E402
from runtime.ledger import Ledger  # noqa: E402
from runtime.runner import run_batch  # noqa: E402
from runtime.verify import run_verify  # noqa: E402


def _build_verify(entity, env: dict, base: Path):
    spec = entity.verify
    if not spec:
        return None
    prefix = env.get("db_prefix")
    database = env.get("database")
    if not prefix or not database:
        return None
    db_env = load_env(base / ".env")

    def verify(ctx):
        conn = db.connect(db_env, prefix, database)
        try:
            return run_verify(conn, spec, {"no": ctx.get("external_no", "")})
        finally:
            conn.close()

    return verify


def main(argv: list[str] | None = None, client_factory=None) -> int:
    parser = argparse.ArgumentParser(description="按适配层批量造数")
    parser.add_argument("--project", required=True)
    parser.add_argument("--entity", required=True)
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--run-id")
    parser.add_argument("--env", default="dev")
    args = parser.parse_args(argv)

    adapter = load_adapter(args.project)
    if args.entity not in adapter.entities:
        parser.error(f"未知业务对象 {args.entity}，可选：{', '.join(adapter.entities)}")
    entity = adapter.entities[args.entity]

    env = adapter.envs.get(args.env)
    if not env:
        parser.error(f"未知环境 {args.env}")

    base = project_dir(args.project)
    if client_factory is None:
        auth = build_auth(adapter.auth, base)
        client_factory = lambda: HttpClient(env["base_url"], auth=auth)  # noqa: E731

    run_id = args.run_id or datetime.now().strftime("%m%d%H%M%S")
    ledger = Ledger(base / "ledger.csv")
    result = run_batch(
        entity, client_factory, args.count, args.workers, run_id, ledger,
        impl_root=base, verify=_build_verify(entity, env, base),
    )

    print(f"run_id={run_id} done={result['done']} failed={result['failed']}")
    for idx, reason in result["failures"][:20]:
        print(f"  idx={idx}: {reason}")
    return 0 if result["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
