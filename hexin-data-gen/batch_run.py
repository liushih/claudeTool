"""批量造「已上传」提货单：多线程 + CSV 台账 + 断点续跑。

用法：
  python batch_run.py --count 500 --workers 5
  python batch_run.py --count 500 --workers 5 --run-id 10211405   # 续跑同一批
"""

from __future__ import annotations

import argparse
import csv
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

from chain import ChainError, run_chain
from hexin_client import HexinClient

LEDGER = Path(__file__).with_name("batch_ledger.csv")
FIELDS = [
    "run_id", "idx", "external_no", "order_id", "order_no", "package_nos",
    "out_nos", "picking_order_no", "delivery_nos", "stage", "status", "error", "updated_at",
]

_lock = threading.Lock()


def read_done(run_id: str) -> set[int]:
    done: set[int] = set()
    if not LEDGER.exists():
        return done
    with LEDGER.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            if row.get("run_id") == run_id and row.get("status") == "done":
                done.add(int(row["idx"]))
    return done


def append_row(row: dict) -> None:
    with _lock:
        new_file = not LEDGER.exists()
        with LEDGER.open("a", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=FIELDS)
            if new_file:
                writer.writeheader()
            writer.writerow(row)


def snapshot(run_id: str, idx: int, ctx: dict, status: str, error: str = "") -> None:
    packages = ctx.get("packages") or []
    append_row({
        "run_id": run_id,
        "idx": idx,
        "external_no": ctx.get("external_no", ""),
        "order_id": ctx.get("order_id", ""),
        "order_no": ctx.get("order_no", ""),
        "package_nos": "|".join(p.get("package_no", "") for p in packages),
        "out_nos": "|".join(p.get("out_no", "") for p in packages if p.get("out_no")),
        "picking_order_no": "|".join(ctx.get("picking_order_nos") or []),
        "delivery_nos": "|".join(ctx.get("delivery_nos") or []),
        "stage": ctx.get("stage", ""),
        "status": status,
        "error": error,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })


def worker(run_id: str, indexes: list[int], counter: dict, failures: list) -> None:
    client = HexinClient()
    for idx in indexes:
        external_no = f"PB{run_id}{idx:04d}"
        ctx: dict = {"external_no": external_no}
        try:
            run_chain(client, external_no, ctx=ctx,
                      on_stage=lambda c: snapshot(run_id, idx, c, "running"))
            snapshot(run_id, idx, ctx, "done")
            with _lock:
                counter["done"] += 1
                print(f"  [{counter['done']}/{counter['total']}] idx={idx} 提货单={'|'.join(ctx.get('delivery_nos') or [])}", flush=True)
        except ChainError as exc:
            snapshot(run_id, idx, ctx, "failed", str(exc))
            with _lock:
                counter["failed"] += 1
                failures.append((idx, str(exc)))
                print(f"  [FAIL] idx={idx} {exc}", flush=True)
        except Exception as exc:  # noqa: BLE001
            snapshot(run_id, idx, ctx, "failed", f"{type(exc).__name__}: {exc}")
            with _lock:
                counter["failed"] += 1
                failures.append((idx, f"{type(exc).__name__}: {exc}"))
                print(f"  [ERROR] idx={idx} {exc}", flush=True)
                traceback.print_exc()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=500)
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--run-id", default=datetime.now().strftime("%m%d%H%M%S"))
    args = parser.parse_args()

    done = read_done(args.run_id)
    todo = [i for i in range(args.count) if i not in done]
    print(f"run_id={args.run_id} 目标 {args.count} 张，已完成 {len(done)}，本次待跑 {len(todo)}，并发 {args.workers}")

    if not todo:
        print("没有需要跑的单")
        return

    chunks = [todo[i::args.workers] for i in range(args.workers)]
    counter = {"done": 0, "failed": 0, "total": len(todo)}
    failures: list = []
    started = time.time()

    threads = [
        threading.Thread(target=worker, args=(args.run_id, chunk, counter, failures), daemon=True)
        for chunk in chunks if chunk
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    elapsed = time.time() - started
    print(f"\n完成 {counter['done']} 张，失败 {counter['failed']} 张，耗时 {elapsed / 60:.1f} 分钟")
    if failures:
        print("失败明细：")
        for idx, reason in failures[:20]:
            print(f"  idx={idx}: {reason}")
    print(f"台账：{LEDGER}")


if __name__ == "__main__":
    main()
