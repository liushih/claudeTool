"""汇总 db_audit.json：剔除被后续脚本删改导致的假未执行，输出报告数据。"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

TOOL = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOL.parent))
from hxpaths import REPO  # noqa: E402
rows = json.loads((TOOL / "db_audit.json").read_text(encoding="utf-8"))
ledger_rows = json.loads((TOOL / "ledger.json").read_text(encoding="utf-8"))
led = {}
for r in ledger_rows:
    p = r[1].strip().replace("\\", "/")
    if p:
        led[p] = {"task": r[0], "dev": r[4], "test": r[5], "prod": r[7], "note": r[8]}

# name -> last date it was dropped/renamed
SUPERSEDED: dict[str, str] = {}


def note(name: str, date: str):
    if not name:
        return
    if date > SUPERSEDED.get(name, ""):
        SUPERSEDED[name] = date


def collect():
    for p in REPO.glob("script/sql/releases/20*/**/*.sql"):
        rel = p.relative_to(REPO).as_posix()
        m = re.search(r"/releases/(\d{4}-\d{2}-\d{2})/", rel)
        if not m:
            continue
        date = m.group(1)
        text = p.read_text(encoding="utf-8", errors="ignore")
        text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
        text = re.sub(r"--[^\n]*", " ", text)
        for mm in re.finditer(r"(?i)\bdrop\s+index\s+(?:concurrently\s+)?(?:if\s+exists\s+)?([\w\".]+)", text):
            note(mm.group(1).strip('"').split(".")[-1], date)
        for mm in re.finditer(r"(?i)\bdrop\s+table\s+(?:if\s+exists\s+)?([\w\".]+)", text):
            note(mm.group(1).strip('"').split(".")[-1], date)
        for mm in re.finditer(r"(?i)\bdrop\s+column\s+(?:if\s+exists\s+)?([\w\"]+)", text):
            note(mm.group(1).strip('"'), date)
        for mm in re.finditer(r"(?i)\brename\s+column\s+([\w\"]+)\s+to\s+([\w\"]+)", text):
            note(mm.group(1).strip('"'), date)
        for mm in re.finditer(r"(?i)\brename\s+to\s+([\w\"]+)", text):
            pass
        for mm in re.finditer(r"(?i)\bdrop\s+constraint\s+(?:if\s+exists\s+)?([\w\"]+)", text):
            note(mm.group(1).strip('"'), date)


def probe_name(p: dict) -> str:
    return p.get("name") or p.get("table") or ""


def reclassify(row: dict) -> dict:
    m = re.search(r"/releases/(\d{4}-\d{2}-\d{2})/", row["path"])
    date = m.group(1) if m else "9999-99-99"
    for env in ("dev", "test", "prod"):
        if row[env] not in ("未执行", "部分执行"):
            continue
        failed = row.get("diag", {}).get(env, [])
        if not failed:
            continue
        names = []
        for f in failed:
            f = f.split(":", 1)[1]
            names.append(f.split(".")[-1])
        if all(SUPERSEDED.get(n, "") > date for n in names):
            row[env] = "已执行(后续删改)"
    return row


collect()
rows = [reclassify(r) for r in rows]
json.dump(rows, open(TOOL / "db_audit_final.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

print("== 最终统计（回滚已排除） ==")
for env in ("dev", "test", "prod"):
    print(env, dict(Counter(r[env] for r in rows)))

for env in ("dev", "test", "prod"):
    print(f"\n== {env} 待处理（未执行/部分执行） ==")
    for r in rows:
        if r[env] in ("未执行", "部分执行"):
            d = ";".join(r.get("diag", {}).get(env, [])[:4])
            print(f"  [{r[env]}] {r['path']} | 台账 {r['ledger']} | {d}")

print("\n== prod 按日期包统计（未执行/部分） ==")
per = defaultdict(Counter)
for r in rows:
    if r["prod"] in ("未执行", "部分执行"):
        m = re.search(r"/releases/(\d{4}-\d{2}-\d{2})/", r["path"])
        per[m.group(1) if m else "?"][r["prod"]] += 1
for d in sorted(per):
    print(f"  {d}: {dict(per[d])}")

print("\n== 未登记台账（非回滚） ==")
for r in rows:
    if r["ledger"] == "未登记":
        print(f"  {r['path']} | dev={r['dev']} test={r['test']} prod={r['prod']}")
