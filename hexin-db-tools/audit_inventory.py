"""盘点 releases 脚本 × 飞书台账：缺失登记、缺失脚本、回滚配对、分类统计。"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hxpaths import REPO  # noqa: E402
RELEASES = REPO / "script/sql/releases"
LEDGER = Path(__file__).with_name("ledger.json")

DESTRUCTIVE = re.compile(
    r"(?im)^\s*(drop\s+(table|column|index|constraint)|truncate\s+table|delete\s+from|update\s+\S+\s+set)\b"
)
MYSQL_ONLY = re.compile(r"(?i)\b(sysdate|ifnull|date_format|date_add|group_concat)\s*\(|\bset\s+@\w+\s*:=|\bSET\s+@\w+\s*=")


def is_rollback(path: str) -> bool:
    return Path(path).name.lower().endswith("_rollback.sql") or "/rollback/" in path.lower()


def kind(path: str) -> str:
    if is_rollback(path):
        return "rollback"
    for t in ("dml/dict", "dml/menu", "dml/perm", "dml/seed", "dml/migrate", "dml/config", "validate"):
        if f"/{t}/" in path:
            return t
    if "/ddl/" in path:
        return "ddl"
    return "dml/other"


def main():
    disk = sorted(p.relative_to(REPO).as_posix() for p in RELEASES.glob("20*/**/*.sql"))
    ledger_rows = json.loads(LEDGER.read_text(encoding="utf-8"))
    led = {}
    for r in ledger_rows:
        path = r[1].strip().replace("\\", "/")
        if path:
            led[path] = {"task": r[0], "dev": r[4], "test": r[5], "uat": r[6], "prod": r[7], "note": r[8]}

    disk_set = set(disk)
    led_set = set(led)

    print(f"磁盘脚本 {len(disk)}；台账行 {len(led)}")
    print("\n== 分类统计 ==")
    print(Counter(kind(p) for p in disk))

    missing_ledger = [p for p in disk if p not in led_set]
    missing_disk = [p for p in led_set if p not in disk_set and p.startswith("script/sql/releases/")]
    print(f"\n== 未登记台账 {len(missing_ledger)} ==")
    for p in missing_ledger:
        print(" ", p)
    print(f"\n== 台账有、磁盘无 {len(missing_disk)} ==")
    for p in missing_disk:
        print(" ", p, led[p])

    print("\n== 台账登记但磁盘缺失（含非 releases 路径） ==")
    for p in sorted(led_set - disk_set):
        print(" ", p, led[p])

    # rollback pairing
    print("\n== 回滚脚本 ==")
    for p in disk:
        if kind(p) != "rollback":
            continue
        base = re.sub(r"_rollback(?=\.sql$)", "", p)
        exists = base in disk_set
        print(f"  {p}\n    base={'存在' if exists else '缺失'} {base}\n    ledger={led.get(p)}")

    # destructive scripts without rollback
    print("\n== 破坏性脚本（DROP/TRUNCATE/DELETE/UPDATE） ==")
    for p in disk:
        if kind(p) == "rollback":
            continue
        text = (REPO / p).read_text(encoding="utf-8", errors="ignore")
        if DESTRUCTIVE.search(text):
            rb = re.sub(r"\.sql$", "_rollback.sql", p)
            rb2 = re.sub(r"/ddl/([^/]+)\.sql$", r"/ddl/\1_rollback.sql", p)
            has_rb = rb in disk_set or rb2 in disk_set
            print(f"  {p} | rollback={'有' if has_rb else '无'} | {led.get(p, {}).get('dev', '-')}/{led.get(p, {}).get('test', '-')}/{led.get(p, {}).get('prod', '-')}")

    # migrate / seed inventory with status
    for k in ("dml/migrate", "validate", "dml/seed", "dml/other"):
        print(f"\n== {k} ==")
        for p in disk:
            if kind(p) != k:
                continue
            s = led.get(p)
            status = f"{s['dev']}/{s['test']}/{s['prod']}" if s else "未登记"
            print(f"  {p} | {status}")

    # MySQL dialect
    print("\n== MySQL 方言脚本（不应在 PG 执行） ==")
    for p in disk:
        text = (REPO / p).read_text(encoding="utf-8", errors="ignore")
        if MYSQL_ONLY.search(text):
            print(f"  {p} | {led.get(p, '未登记')}")


if __name__ == "__main__":
    main()
