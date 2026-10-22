"""全量脚本三环境差异归类（读 sync_all.txt，不连库）。"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path

TOOL = Path(__file__).resolve().parent
REPO = Path(r"C:/project/hexincloud")
RAW = (TOOL / "sync_all.txt").read_text(encoding="gbk", errors="replace")

HEAD_RE = re.compile(r"^(script/sql/releases/(\d{4}-\d{2}-\d{2})/([^/]+)/([^/]+)/(\S+\.sql))\s+(\S+)\s+(\S+)\s+(.+?)\s*$")

rows = []
for line in RAW.splitlines():
    m = HEAD_RE.match(line.strip())
    if not m:
        continue
    path, date, module, kind, fname, k2, dialect, rest = m.groups()
    pads = re.findall(r"(已执行|部分执行|未执行|无法校验|不应执行|无|\?)", rest)
    if len(pads) < 3:
        continue
    rows.append(dict(path=path, date=date, module=module, kind=kind, dtype=k2,
                     dialect=dialect, dev=pads[0], test=pads[1], prod=pads[2]))

print("scripts:", len(rows))
print("pattern counts:")
for pat, n in Counter((r["dev"], r["test"], r["prod"]) for r in rows).most_common():
    print("  ", pat, n)

def is_new_table(r):
    txt = (REPO / r["path"]).read_text(encoding="utf-8", errors="ignore").lower()
    return r["kind"] == "ddl" and "create table" in txt

def has_alter(r):
    t = (REPO / r["path"]).read_text(encoding="utf-8", errors="ignore").lower()
    return "alter table" in t

def size(r):
    p = REPO / r["path"]
    stem = p.stem
    if stem.endswith("_rollback"):
        return "rollback"
    return r["kind"]

# Prod-missing where dev&test both executed
prod_gap = [r for r in rows if r["prod"] in ("未执行", "部分执行", "无法校验")
            and r["dev"] == "已执行" and r["test"] == "已执行"]
by_date = defaultdict(list)
for r in prod_gap:
    by_date[r["date"]].append(r)

print("\n=== prod 缺口（dev+test 均已执行，prod 未/部分/无法校验）:", len(prod_gap))
for d in sorted(by_date):
    items = by_date[d]
    kinds = Counter(size(r) for r in items)
    print(f"\n## {d}  ({len(items)})  {dict(kinds)}")
    for r in sorted(items, key=lambda x: x["path"]):
        p = REPO / r["path"]
        flag = ""
        txt = p.read_text(encoding="utf-8", errors="ignore")
        low = txt.lower()
        if "create table" in low and "alter table" not in low:
            flag += "NEW-TABLE "
        elif "create table" in low:
            flag += "NEW+ALTER "
        elif "alter table" in low:
            flag += "ALTER "
        if re.search(r"(?i)^\s*update\s", txt, re.M):
            flag += "UPDATE-DATA "
        if re.search(r"(?i)^\s*delete\s", txt, re.M):
            flag += "DELETE-DATA "
        if re.search(r"(?i)^\s*insert\s", txt, re.M):
            flag += "INSERT "
        print(f"  {r['prod']:6} {flag:26} {r['path']}")

# dev vs test mismatch
print("\n=== dev/test 不一致 ===")
for r in rows:
    if r["dev"] != r["test"]:
        print(f"  dev={r['dev']:6} test={r['test']:6} prod={r['prod']:6} {r['path']}")

# unverifiable aggregated
print("\n=== 无法校验（103）按日期 ===")
unv = [r for r in rows if "无法校验" in (r["dev"], r["test"], r["prod"])]
for d, n in sorted(Counter(r["date"] for r in unv).items()):
    print(f"  {d}: {n}")
