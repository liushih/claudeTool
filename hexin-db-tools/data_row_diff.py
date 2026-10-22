"""比对 test 有、prod 无的菜单权限 / 字典类型 / 配置项，并检查是否有脚本覆盖。只读。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hxpaths import REPO  # noqa: E402
import sql_sync_check as c  # noqa: E402
SCRIPTS = list((REPO / "script/sql").rglob("*.sql")) + [
    p for p in (REPO / "hexin-modules").rglob("*.sql") if "target" not in p.parts
]
BLOB = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in SCRIPTS)
BLOB_LOW = BLOB.lower()


def fetch(env: str, sql: str):
    with c.connect(env, "hexin_masterdata") as conn:
        return {r[0] for r in conn.execute(sql) if r[0] not in (None, "")}


def check(label: str, sql: str, pattern: str):
    test = fetch("test", sql)
    prod = fetch("prod", sql)
    missing = sorted(test - prod)
    no_script = [x for x in missing if not re.search(pattern.format(re.escape(x)), BLOB, re.I)]
    print(f"\n=== {label}: test {len(test)} / prod {len(prod)} / test有prod无 {len(missing)} / 其中无脚本 {len(no_script)} ===")
    for x in no_script:
        print(f"  无脚本  {x}")
    return missing, no_script


check("菜单权限 perms", "select distinct perms from sys_menu where perms is not null and perms <> ''", r"\b{}\b")
check("字典类型 dict_type", "select distinct dict_type from sys_dict_type", r"\b{}\b")
check("配置项 config_key", "select distinct config_key from sys_config", r"\b{}\b")
