"""核实：无建表脚本的表在三个环境是否真实存在（含非 public schema）。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sql_sync_check as c  # noqa: E402

ENVS = ["dev", "test", "prod"]
TABLES = [
    "ods_fbt_outbound_order_base", "ods_fbt_return_orders_report",
    "report_fba_fulfillment_customer_returns_v5", "report_fba_fulfillment_removal_order_detail_v5",
    "report_fba_removal_shipment_detail_v5", "report_fulfilled_shipments_data_general_v5",
    "report_ledger_detail_view_data_v5", "report_ledger_summary_view_monthly_data_v5",
    "sys_data_change_log", "sys_exception_action_config", "sys_exception_action_log",
    "sys_exception_action_task", "sys_exception_log", "flow_instance_biz_ext",
    "flow_spel", "process_node", "wms_inventory_global", "oms_upload_file_info",
    "md_logistics_group", "global_stock_erp_product", "global_stock_erp_stock",
    "wms_inventory_summary", "wms_picking_plan", "oms_po_order", "md_customer",
]

SQL = """
select n.nspname, c.relname, c.relkind
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where c.relname = any(%s) and n.nspname not in ('pg_catalog','information_schema')
order by 1,2
"""

for env in ENVS:
    print(f"\n===== {env} =====")
    with c.connect(env, "postgres") as conn:
        dbs = [r[0] for r in conn.execute(
            "select datname from pg_database where datistemplate=false and datname not in ('postgres')")]
    hits = {}
    for db in dbs:
        try:
            with c.connect(env, db) as conn:
                for ns, rel, kind in conn.execute(SQL, (TABLES,)):
                    hits.setdefault(rel, []).append(f"{db}.{ns}({kind})")
        except Exception as e:
            print(f"  !! {db}: {str(e).splitlines()[0][:80]}")
    for t in TABLES:
        print(f"  {t:52} {', '.join(hits.get(t, [])) or '—— 不存在'}")

# 列核对
COLS = {
    "global_stock_erp_product": ["level0_category", "level4_category"],
    "global_stock_erp_stock": ["unpicked_quantity_long"],
    "wms_inventory_summary": ["product_category_id", "production_type"],
    "wms_picking_plan": ["ck_end_time"],
    "oms_po_order": ["bill_day", "invoice_title", "payment_account_id"],
    "md_customer": ["customer_type", "store_id", "credit_limit"],
}
DB_OF = {
    "global_stock_erp_product": "hexin_masterdata", "global_stock_erp_stock": "hexin_masterdata",
    "wms_inventory_summary": "hexin_wms", "wms_picking_plan": "hexin_wms",
    "oms_po_order": "hexin_oms", "md_customer": "hexin_masterdata",
}
print("\n===== 列核对 =====")
for t, cols in COLS.items():
    row = [f"{t}"]
    for env in ENVS:
        try:
            with c.connect(env, DB_OF[t]) as conn:
                got = {r[0] for r in conn.execute(
                    "select column_name from information_schema.columns where table_name=%s", (t,))}
            row.append(f"{env}=" + ("有" if set(cols) <= got else "缺:" + ",".join(sorted(set(cols) - got))))
        except Exception as e:
            row.append(f"{env}=ERR({str(e).splitlines()[0][:40]})")
    print("  " + " | ".join(row))
