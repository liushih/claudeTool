"""三环境库结构全量比对：表 / 列。只读。"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sql_sync_check as c  # noqa: E402

ENVS = ["dev", "test", "prod"]
DBS = ["hexin_oms", "hexin_wms", "hexin_masterdata", "hexin_openapi",
       "hexin_job", "hexin_log", "hexin_resource", "hexin_workflow"]
SKIP_SCHEMA = ("pg_catalog", "information_schema")

TAB_SQL = """
select table_name from information_schema.tables
where table_schema='public' and table_type='BASE TABLE'
"""
COL_SQL = """
select table_name, column_name, data_type, is_nullable
from information_schema.columns where table_schema='public'
"""

snap = {}
for env in ENVS:
    snap[env] = {}
    for db in DBS:
        try:
            with c.connect(env, db) as conn:
                tabs = {r[0] for r in conn.execute(TAB_SQL)}
                cols = {(r[0], r[1]): (r[2], r[3]) for r in conn.execute(COL_SQL)}
            snap[env][db] = {"tabs": tabs, "cols": cols}
        except Exception as e:
            print(f"!! {env}/{db}: {str(e).splitlines()[0][:100]}", file=sys.stderr)
            snap[env][db] = {"tabs": set(), "cols": {}}

ERP_PREFIX = ("ods_", "report_", "global_stock_erp_", "erp_", "dw_", "dwd_", "dws_", "ads_")


def out(title, lines):
    print(f"\n=== {title} ({len(lines)}) ===")
    for x in lines:
        print("  " + x)


only_prod, only_dev, only_test = [], [], []
col_only_prod, col_only_devtest, col_prod_ahead = [], [], []
type_diff = []

for db in DBS:
    d, t, p = snap["dev"][db], snap["test"][db], snap["prod"][db]
    for tab in sorted(d["tabs"] | t["tabs"] | p["tabs"]):
        has = {"dev": tab in d["tabs"], "test": tab in t["tabs"], "prod": tab in p["tabs"]}
        if has["dev"] and has["test"] and not has["prod"]:
            if tab.startswith(ERP_PREFIX):
                only_prod.append(f"[ERP] {db}.{tab}")
            else:
                only_prod.append(f"{db}.{tab}")
        elif not has["dev"] and has["test"]:
            only_test.append(f"{db}.{tab}")
        elif has["dev"] and not has["test"]:
            only_dev.append(f"{db}.{tab}")
    # columns only when table exists in all envs
    for tab in sorted(d["tabs"] & t["tabs"] & p["tabs"]):
        dc = {k[1]: v for k, v in d["cols"].items() if k[0] == tab}
        tc = {k[1]: v for k, v in t["cols"].items() if k[0] == tab}
        pc = {k[1]: v for k, v in p["cols"].items() if k[0] == tab}
        dt_missing = sorted(set(dc) - set(pc))
        if dt_missing:
            tag = "[ERP]" if tab.startswith(ERP_PREFIX) else ""
            col_only_prod.append(f"{tag}{db}.{tab}: {', '.join(dt_missing)}")
        prod_extra = sorted(set(pc) - set(dc))
        if prod_extra:
            col_prod_ahead.append(f"{db}.{tab}: {', '.join(prod_extra)}")
        # dev vs test column diff
        ds, ts = set(dc) - set(tc), set(tc) - set(dc)
        if ds or ts:
            col_only_devtest.append(f"{db}.{tab}: dev独有={sorted(ds)} test独有={sorted(ts)}")
        for cname in set(dc) & set(tc) & set(pc):
            if dc[cname][0] != pc[cname][0] or dc[cname][1] != pc[cname][1]:
                type_diff.append(f"{db}.{tab}.{cname}: dev={dc[cname]} prod={pc[cname]}")

out("dev+test 有、prod 缺的表", only_prod)
out("dev 有、test 缺的表", only_dev)
out("test 有、dev 缺的表", only_test)
out("dev/test 有、prod 缺的列", col_only_prod)
out("prod 有、dev 缺的列（prod 反超）", col_prod_ahead)
out("dev/test 列不一致", col_only_devtest)
out("dev/prod 列类型或可空性不一致（抽样 120）", type_diff[:120])
