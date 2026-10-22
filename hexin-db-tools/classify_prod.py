"""对 prod 缺口脚本做执行方式归类。"""
from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sql_sync_check as c  # noqa: E402

TOOL = Path(__file__).resolve().parent
REPO = Path(r"C:/project/hexincloud")
RAW = (TOOL / "sync_all.txt").read_text(encoding="gbk", errors="replace")
HEAD_RE = re.compile(r"^(script/sql/releases/(\d{4}-\d{2}-\d{2})/([^/]+)/([^/]+)/(\S+\.sql))\s+(\S+)\s+(\S+)\s+(.+?)\s*$")

rows = []
for line in RAW.splitlines():
    m = HEAD_RE.match(line.strip())
    if not m:
        continue
    path, date, module, kind, fname, dtype, dialect, rest = m.groups()
    pads = re.findall(r"(已执行|部分执行|未执行|无法校验|不应执行|无|\?)", rest)
    if len(pads) < 3:
        continue
    rows.append(dict(path=path, date=date, module=module, kind=kind, dtype=dtype,
                     dev=pads[0], test=pads[1], prod=pads[2]))

# prod 表清单
DBS = ["hexin_oms", "hexin_wms", "hexin_masterdata", "hexin_openapi", "hexin_job",
       "hexin_log", "hexin_resource", "hexin_workflow"]
prod_tables = set()
for db in DBS:
    with c.connect("prod", db) as conn:
        prod_tables |= {r[0] for r in conn.execute(
            "select table_name from information_schema.tables where table_schema='public' and table_type='BASE TABLE'")}

TAB = re.compile(r'(?is)\b(?:create\s+table(?:\s+if\s+not\s+exists)?|alter\s+table(?:\s+if\s+exists)?|insert\s+into|update|delete\s+from|truncate(?:\s+table)?)\s+(?:"?public"?\.)?"?([a-z_][\w$]*)"?')
ERP = re.compile(r"(?i)\b(ods_|report_|global_stock_erp_)")


def classify(r):
    text = (REPO / r["path"]).read_text(encoding="utf-8", errors="ignore")
    low = text.lower()
    kind = r["dtype"]
    if kind.startswith("dml/"):
        sub = kind.split("/", 1)[1]
        if sub in ("dict", "menu", "perm", "config"):
            return sub
        if sub == "seed":
            return "seed"
        if sub == "migrate":
            tabs = [t.lower() for t in TAB.findall(text)]
            if any(ERP.search(t) for t in tabs):
                return "erp-migrate"
            return "data-fix"
        tabs = [t.lower() for t in TAB.findall(text)]
        if any(re.search(r"(?i)^\s*(update|delete)", s) for s in text.split(";")):
            return "data-fix"
        return "dml-other"
    if kind == "ddl":
        creates = re.findall(r"(?is)create\s+table\s+(?:if\s+not\s+exists\s+)?(?:\"?public\"?\.)?\"?([a-z_][\w$]*)\"?", text)
        alters = re.findall(r"(?is)alter\s+table\s+(?:if\s+exists\s+)?(?:\"?public\"?\.)?\"?([a-z_][\w$]*)\"?", text)
        has_idx = re.search(r"(?i)create\s+(unique\s+)?index", text) is not None
        has_data = re.search(r"(?im)^\s*(update|delete|truncate)\b", text) is not None
        new = [t for t in creates if t.lower() not in prod_tables]
        existing_alter = [t for t in alters if t.lower() in prod_tables]
        if has_data and not creates and not alters:
            return "data-fix"
        if creates and not existing_alter:
            if any(ERP.search(t) for t in creates):
                return "erp-new-table"
            return "new-table"
        if existing_alter:
            return "alter-existing"
        if has_idx and not creates:
            return "index-only"
        if creates and existing_alter:
            return "new+alter-existing"
        return "ddl-other"
    return kind


gaps = [r for r in rows if r["prod"] in ("未执行", "部分执行") and r["dev"] == "已执行" and r["test"] == "已执行"]
print(f"prod 缺口脚本（dev+test 已执行、prod 未/部分）: {len(gaps)}\n")
cat = Counter()
bycat = defaultdict(list)
for r in gaps:
    k = classify(r)
    cat[k] += 1
    bycat[k].append(r)
for k, n in cat.most_common():
    print(f"  {k:22} {n}")

print("\n=== 各类脚本的日包分布 ===")
for k in cat:
    dates = sorted({r["date"] for r in bycat[k]})
    print(f"  {k:22} {dates[0]} ~ {dates[-1]} ({len(dates)} 个日包)")

print("\n=== 修数据 / ERP 迁移类明细 ===")
for k in ("data-fix", "erp-migrate", "seed"):
    for r in bycat.get(k, []):
        print(f"  [{k:10}] {r['prod']:4} {r['path']}")

print("\n=== 已有表 ALTER 明细（prod 必做，逐条评估） ===")
for r in bycat.get("alter-existing", []) + bycat.get("new+alter-existing", []):
    text = (REPO / r["path"]).read_text(encoding="utf-8", errors="ignore")
    alters = sorted(set(t.lower() for t in re.findall(
        r"(?is)alter\s+table\s+(?:if\s+exists\s+)?(?:\"?public\"?\.)?\"?([a-z_][\w$]*)\"?", text) if t.lower() in prod_tables))
    print(f"  {r['path']}  -> {', '.join(alters)}")
