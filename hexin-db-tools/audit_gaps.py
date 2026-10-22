"""细分：dev 未执行 / 部分执行 / 无法校验 / dev-test 不一致。"""
from __future__ import annotations

import re
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
    path, date, module, kind, fname, dtype, dialect, rest = m.groups()
    pads = re.findall(r"(已执行|部分执行|未执行|无法校验|不应执行|无|\?)", rest)
    if len(pads) < 3:
        continue
    rows.append(dict(path=path, date=date, module=module, kind=kind, dev=pads[0], test=pads[1], prod=pads[2]))

def brief(p):
    t = (REPO / p).read_text(encoding="utf-8", errors="ignore")
    kinds = []
    low = t.lower()
    if "create table" in low: kinds.append("CREATE")
    if "alter table" in low: kinds.append("ALTER")
    if re.search(r"(?m)^\s*update\s", t, re.I): kinds.append("UPDATE")
    if re.search(r"(?m)^\s*delete\s", t, re.I): kinds.append("DELETE")
    if re.search(r"(?m)^\s*insert\s", t, re.I): kinds.append("INSERT")
    if "sys_dict" in low: kinds.append("sys_dict")
    if "sys_menu" in low: kinds.append("sys_menu")
    if "sys_role_menu" in low: kinds.append("sys_role_menu")
    if "sys_config" in low: kinds.append("sys_config")
    return "/".join(kinds) or "?"

def show(title, items):
    print(f"\n=== {title} ({len(items)}) ===")
    for r in items:
        print(f"  {r['date']} {r['kind']:10} dev={r['dev']:5} test={r['test']:5} prod={r['prod']:5} | {brief(r['path']):32} | {r['path']}")

show("dev 未执行（三环境都未执行）", [r for r in rows if r["dev"] == "未执行"])
show("dev 部分执行", [r for r in rows if r["dev"] == "部分执行"])
show("无法校验", [r for r in rows if r["dev"] == "无法校验"])
show("dev/test 不一致", [r for r in rows if r["dev"] != r["test"]])
show("不应执行", [r for r in rows if "不应执行" in (r["dev"], r["test"], r["prod"])])
