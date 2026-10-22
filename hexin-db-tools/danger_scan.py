"""扫描 releases 脚本中的破坏性语句，并核对目标表在 prod 是否存在。只读。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hxpaths import REPO  # noqa: E402
import sql_sync_check as c  # noqa: E402
RELEASES = REPO / "script/sql/releases"
MODULE_DB = {
    "oms": "hexin_oms", "wms": "hexin_wms", "hexin-wms": "hexin_wms",
    "masterdata": "hexin_masterdata", "openapi": "hexin_openapi", "job": "hexin_job",
    "log": "hexin_log", "resource": "hexin_resource", "workflow": "hexin_workflow",
    "system": "hexin_masterdata", "gen": "hexin_gen", "config": "hexin_config",
}
DBS = sorted(set(MODULE_DB.values()))

# prod 表清单
prod = {}
for db in DBS:
    try:
        with c.connect("prod", db) as conn:
            prod[db] = {r[0] for r in conn.execute(
                "select table_name from information_schema.tables where table_schema='public' and table_type='BASE TABLE'")}
    except Exception:
        prod[db] = set()

ALL = set().union(*prod.values())

IDENT = r'("?[A-Za-z_][\w$]*"?(?:\."?[A-Za-z_][\w$]*"?)?)'
PATTERNS = [
    ("DROP TABLE", re.compile(r"(?im)^\s*drop\s+table\s+(?:if\s+exists\s+)?" + IDENT)),
    ("TRUNCATE", re.compile(r"(?im)^\s*truncate\s+(?:table\s+)?" + IDENT)),
    ("DELETE", re.compile(r"(?im)^\s*delete\s+from\s+" + IDENT)),
    ("DROP COLUMN", re.compile(r"(?i)\bdrop\s+column\s+(?:if\s+exists\s+)?" + IDENT)),
]
UPDATE = re.compile(r"(?im)^\s*update\s+" + IDENT + r"\s+set\b(.*?)(;|$)", re.S)

def db_of(path: str) -> str | None:
    parts = path.split("/")
    return MODULE_DB.get(parts[4]) if len(parts) > 4 else None

def norm(x: str) -> str:
    return x.strip().strip('"').split(".")[-1].strip('"')

rows = []
for p in sorted(RELEASES.glob("20*/**/*.sql")):
    rel = p.relative_to(REPO).as_posix()
    if rel.endswith("_rollback.sql") or "/rollback/" in rel:
        continue
    text = p.read_text(encoding="utf-8", errors="ignore")
    db = db_of(rel)
    for label, pat in PATTERNS:
        for m in pat.finditer(text):
            t = norm(m.group(1))
            if t.lower() in ("table",):
                continue
            rows.append((label, rel, t, t in prod.get(db, set()) if db else None))
    for m in UPDATE.finditer(text):
        t = norm(m.group(1))
        body = m.group(2)
        has_where = re.search(r"(?i)\bwhere\b", body)
        rows.append(("UPDATE-no-WHERE" if not has_where else "UPDATE", rel, t,
                     t in prod.get(db, set()) if db else None))

print(f"命中破坏性/数据修正语句 {len(rows)} 处；prod 已存在目标表的：")
risk = [r for r in rows if r[3] and r[0] in ("DROP TABLE", "TRUNCATE", "DELETE", "DROP COLUMN")]
print(f"  高风险（prod 表存在且有 DROP/TRUNCATE/DELETE/DROP COLUMN）: {len(risk)}\n")
for label, rel, t, exists in risk:
    print(f"  [{label:11}] prod有={exists} {t:45} {rel}")

print("\n=== UPDATE 无 WHERE ===")
for label, rel, t, exists in rows:
    if label == "UPDATE-no-WHERE":
        print(f"  prod有={exists} {t:45} {rel}")

print("\n=== 其余 DROP/TRUNCATE/DELETE（prod 表不存在或无法确认）===")
for label, rel, t, exists in rows:
    if label in ("DROP TABLE", "TRUNCATE", "DELETE", "DROP COLUMN") and not exists:
        print(f"  [{label:11}] prod有={exists} {t:45} {rel}")

print("\n=== 按脚本汇总 UPDATE/DELETE 数量 ===")
cnt = {}
for label, rel, t, exists in rows:
    if label.startswith("UPDATE") or label == "DELETE":
        cnt[rel] = cnt.get(rel, 0) + 1
for rel, n in sorted(cnt.items()):
    print(f"  {n:2}  {rel}")
