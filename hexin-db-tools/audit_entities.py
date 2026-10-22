"""代码实体 vs dev/test/prod 表结构 vs SQL 脚本覆盖。"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

TOOL = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOL))
sys.path.insert(0, str(TOOL.parent))
from hxpaths import REPO  # noqa: E402
import sql_sync_check as chk  # noqa: E402
MODULES = {
    "hexin-wms": "hexin_wms",
    "hexin-oms": "hexin_oms",
    "hexin-masterdata": "hexin_masterdata",
    "hexin-openapi": "hexin_openapi",
    "hexin-job": "hexin_job",
    "hexin-log": "hexin_log",
    "hexin-resource": "hexin_resource",
    "hexin-workflow": "hexin_workflow",
    "hexin-gen": "hexin_gen",
}
ENVS = ["dev", "test", "prod"]
BASE_COLS = {"create_by", "create_time", "update_by", "update_time", "version"}


def snake(name: str) -> str:
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", s)
    return s.lower()


def parse_entity(path: Path, module_db: str) -> dict | None:
    text = path.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r'@TableName\s*\(\s*(?:value\s*=\s*)?"([^"]+)"', text)
    if not m:
        return None
    table = m.group(1).strip().strip('"')
    if "." in table:
        table = table.split(".")[-1]
    db = module_db
    if table.startswith("sys_"):
        db = "hexin_masterdata"
    cols = set()
    if re.search(r"extends\s+BaseEntity\b", text):
        cols |= BASE_COLS
    pending = []
    for raw in text.splitlines():
        s = raw.strip()
        if not s or s.startswith("//") or s.startswith("*") or s.startswith("/*"):
            continue
        if s.startswith("@"):
            pending.append(s)
            continue
        fm = re.match(r"^(?:private|protected|public)\s+(?!static\b)(?!final\b)(?!transient\b)([\w<>\[\], .?]+?)\s+(\w+)\s*(?:=[^;]*)?;", s)
        if not fm:
            if not pending or (not s.endswith(",") and "=" not in s):
                pending = []
            continue
        _, name = fm.groups()
        ann = " ".join(pending)
        pending = []
        if name in ("serialVersionUID", "searchValue", "params"):
            continue
        if re.search(r"@TableField\s*\(\s*exist\s*=\s*false", ann):
            continue
        cm = re.search(r'@(?:TableField|TableId)\s*\(\s*(?:value\s*=\s*)?"([^"]+)"', ann)
        col = cm.group(1) if cm else snake(name)
        col = col.strip().strip('"').strip("`")
        if col:
            cols.add(col)
    return {"table": table, "db": db, "columns": sorted(cols), "file": str(path.relative_to(REPO))}


def load_entities() -> list[dict]:
    out = []
    for mod, db in MODULES.items():
        root = REPO / "hexin-modules" / mod / "src/main/java"
        if not root.exists():
            continue
        for p in root.rglob("*.java"):
            e = parse_entity(p, db)
            if e:
                out.append(e)
    return out


def load_schema():
    schema = {e: {} for e in ENVS}  # env -> db -> table -> cols
    tables = {e: {} for e in ENVS}  # env -> table -> db
    dbs = sorted(set(MODULES.values()) | {"hexin_config", "hexin_archive"})
    for env in ENVS:
        for db in dbs:
            try:
                with chk.connect(env, db) as cn:
                    for t, c in cn.execute(
                        "select table_name, column_name from information_schema.columns "
                        "where table_schema='public' order by table_name, ordinal_position"
                    ):
                        schema[env].setdefault(db, {}).setdefault(t, set()).add(c)
                        tables[env].setdefault(t, db)
            except Exception:
                continue
    return schema, tables


def load_scripts():
    tables = set()
    cols = set()
    for base in [REPO / "script/sql", REPO / "hexin-modules"]:
        if not base.exists():
            continue
        for p in base.rglob("*.sql"):
            text = p.read_text(encoding="utf-8", errors="ignore")
            text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
            text = re.sub(r"--[^\n]*", " ", text)
            for m in re.finditer(r'(?i)create\s+table\s+(?:if\s+not\s+exists\s+)?([\w".]+)', text):
                t = m.group(1).split(".")[-1].strip('"')
                tables.add(t)
            for m in re.finditer(
                r'(?i)alter\s+table\s+(?:if\s+exists\s+)?([\w".]+)\s+add\s+(?:column\s+)?(?:if\s+not\s+exists\s+)?("?[\w]+"?)',
                text,
            ):
                t = m.group(1).split(".")[-1].strip('"')
                c = m.group(2).strip('"')
                cols.add((t, c))
    return tables, cols


def main():
    entities = load_entities()
    schema, tables = load_schema()
    script_tables, script_cols = load_scripts()
    print(f"实体数 {len(entities)}；脚本建表 {len(script_tables)}；脚本加列 {len(script_cols)}")

    findings = []
    for e in entities:
        t = e["table"]
        db = e["db"]
        present = {env: (t in schema[env].get(db, {})) for env in ENVS}
        missing_t = [env for env in ENVS if not present[env]]
        missing_c = {}
        for env in ENVS:
            if not present[env]:
                continue
            actual = schema[env].get(db, {}).get(t, set())
            mc = [c for c in e["columns"] if c not in actual]
            if mc:
                missing_c[env] = mc
        if missing_t or missing_c:
            findings.append({
                **e,
                "present": present,
                "missing_tables": missing_t,
                "missing_cols": missing_c,
                "scripted_table": t in script_tables,
                "scripted_cols": {c: (t, c) in script_cols for env_cols in missing_c.values() for c in env_cols},
            })

    print(f"有差异的实体 {len(findings)}")
    print("差异类型:", dict(Counter(
        ("表全缺" if set(f["missing_tables"]) == set(ENVS) else "表部分缺" if f["missing_tables"] else "仅列缺")
        for f in findings
    )))
    print("\n=== 表全缺且无脚本（疑似缺 DDL） ===")
    for f in findings:
        if set(f["missing_tables"]) == set(ENVS) and not f["scripted_table"]:
            print(f'  {f["table"]} | {f["db"]} | {f["file"]}')
    print("\n=== 表部分缺且无脚本 ===")
    for f in findings:
        if f["missing_tables"] and set(f["missing_tables"]) != set(ENVS) and not f["scripted_table"]:
            print(f'  {f["table"]} | 缺 {f["missing_tables"]} | {f["db"]} | {f["file"]}')
    print("\n=== 表部分缺但有脚本 ===")
    for f in findings:
        if f["missing_tables"] and set(f["missing_tables"]) != set(ENVS) and f["scripted_table"]:
            print(f'  {f["table"]} | 缺 {f["missing_tables"]} | 有建表脚本 | {f["file"]}')
    print("\n=== 列缺失汇总（无加列脚本的前 60 条） ===")
    n = 0
    for f in findings:
        for env, cs in f["missing_cols"].items():
            for c in cs:
                if not f["scripted_cols"].get(c):
                    print(f'  {f["table"]}.{c} | 缺 {env} | {f["file"]}')
                    n += 1
                    if n >= 60:
                        break
            if n >= 60:
                break
        if n >= 60:
            break
    json.dump(findings, open(TOOL / "entity_audit.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
