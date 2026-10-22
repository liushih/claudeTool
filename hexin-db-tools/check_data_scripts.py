"""逐条检查数据类脚本在 dev/test/prod 的实际执行痕迹。只读。"""
from __future__ import annotations

import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).with_name("sql_sync_check.py")))
import sql_sync_check as c  # noqa: E402

ENVS = ["dev", "test", "prod"]


def q(env: str, db: str, sql: str):
    try:
        with c.connect(env, db) as conn:
            return conn.execute(sql).fetchall()
    except Exception as e:
        return [("ERR", str(e).splitlines()[0][:90])]


def one(env: str, db: str, sql: str):
    r = q(env, db, sql)
    return r[0][0] if r and len(r[0]) == 1 else r


def main():
    checks = []

    # 1 fms table
    checks.append(("2026-07-15 fms_funds_freight_summary", [
        (env, "table", one(env, "hexin_openapi", "select to_regclass('fms_funds_freight_summary')::text")) for env in ENVS
    ]))

    # 2 config
    checks.append(("2026-07-28 logistics.carrier.realApiEnabled", [
        (env, "config", one(env, "hexin_masterdata",
         "select config_value from sys_config where config_key='logistics.carrier.realApiEnabled'")) for env in ENVS
    ]))

    # 3 picking sub order backfill
    rows = []
    for env in ENVS:
        rows.append((env, "sub_order_rows", one(env, "hexin_wms",
            "select count(*) from wms_picking_sub_order where del_flag='0'")))
        rows.append((env, "detail_null_sub_pick_no", one(env, "hexin_wms",
            "select count(*) from wms_picking_detail where del_flag='0' and sub_pick_no is null and picking_order_no is not null")))
        rows.append((env, "main_missing_sub_order", one(env, "hexin_wms",
            """select count(*) from wms_picking_order o
               where o.del_flag='0' and o.picking_order_no is not null
                 and not exists (select 1 from wms_picking_sub_order s
                                 where s.del_flag='0' and s.sub_pick_no=o.picking_order_no)""")))
    checks.append(("2026-08-06 picking_sub_order_backfill", rows))

    # 4/5 indexes
    for label, idx in [
        ("2026-08-14 pda_picking_detail_indexes", "idx_wms_picking_detail_order_sub_sort"),
        ("2026-08-21 pda_b2d_seal_list_indexes", "idx_wms_picking_plan_cker_b2d_outbound"),
    ]:
        checks.append((label, [
            (env, "index", one(env, "hexin_wms",
             f"select count(*) from pg_indexes where schemaname='public' and indexname='{idx}'")) for env in ENVS
        ]))

    # 6 packing batch
    rows = []
    for env in ENVS:
        rows.append((env, "packing_blank", one(env, "hexin_wms",
            "select count(*) from wms_packing where del_flag='0' and (pack_batch_no is null or pack_batch_no='')")))
        rows.append((env, "packing_filled", one(env, "hexin_wms",
            "select count(*) from wms_packing where del_flag='0' and pack_batch_no is not null and pack_batch_no<>''")))
        rows.append((env, "packing_backfill_remaining", one(env, "hexin_wms",
            """select count(*) from wms_packing p
               join (select i.packing_id, min(o.pack_batch_no) as b
                     from wms_packing_item i join wms_order_out o
                       on o.del_flag='0' and o.out_no=i.outbound_order_no
                      and o.pack_batch_no is not null and o.pack_batch_no<>''
                     where i.del_flag='0' group by i.packing_id
                     having count(distinct o.pack_batch_no)=1) src on p.id=src.packing_id
               where p.del_flag='0' and (p.pack_batch_no is null or p.pack_batch_no='')""")))
    checks.append(("2026-08-21 packing_pack_batch_no_backfill", rows))

    # 7 sort status
    sort_conditions = {
        "1 detail FINISH (main SORTING full)": """select count(*) from wms_picking_detail d
            join wms_picking_order o on o.del_flag='0' and d.del_flag='0' and d.picking_order_no=o.picking_order_no
            where o.picking_status='SORTING' and coalesce(d.sort_qty,0)>=coalesce(d.operation_qty,0)
              and coalesce(d.picking_status,'WAIT_SORT') in ('WAIT_SORT','SORTING')""",
        "2 detail SORTING (main SORTING partial)": """select count(*) from wms_picking_detail d
            join wms_picking_order o on o.del_flag='0' and d.del_flag='0' and d.picking_order_no=o.picking_order_no
            where o.picking_status='SORTING' and coalesce(d.sort_qty,0)<coalesce(d.operation_qty,0)
              and d.picking_status='WAIT_SORT'""",
        "3 detail FINISH (main FINISH)": """select count(*) from wms_picking_detail d
            join wms_picking_order o on o.del_flag='0' and d.del_flag='0' and d.picking_order_no=o.picking_order_no
            where o.picking_status='FINISH' and d.picking_status in ('WAIT_SORT','SORTING')""",
        "4 sub FINISH (main SORTING)": """select count(*) from wms_picking_sub_order s
            join wms_picking_order o on o.del_flag='0' and s.del_flag='0' and s.picking_order_no=o.picking_order_no
            where o.picking_status='SORTING' and s.picking_status in ('WAIT_SORT','SORTING')
              and not exists (select 1 from wms_picking_detail d where d.del_flag='0'
                and d.picking_order_no=s.picking_order_no
                and coalesce(d.sub_pick_no,d.picking_order_no)=coalesce(s.sub_pick_no,s.picking_order_no)
                and coalesce(d.sort_qty,0)<coalesce(d.operation_qty,0))""",
        "5 sub SORTING (main SORTING partial)": """select count(*) from wms_picking_sub_order s
            join wms_picking_order o on o.del_flag='0' and s.del_flag='0' and s.picking_order_no=o.picking_order_no
            where o.picking_status='SORTING' and s.picking_status='WAIT_SORT'
              and exists (select 1 from wms_picking_detail d where d.del_flag='0'
                and d.picking_order_no=s.picking_order_no
                and coalesce(d.sub_pick_no,d.picking_order_no)=coalesce(s.sub_pick_no,s.picking_order_no)
                and coalesce(d.sort_qty,0)<coalesce(d.operation_qty,0))""",
        "6 sub FINISH (main FINISH)": """select count(*) from wms_picking_sub_order s
            join wms_picking_order o on o.del_flag='0' and s.del_flag='0' and s.picking_order_no=o.picking_order_no
            where o.picking_status='FINISH' and s.picking_status in ('WAIT_SORT','SORTING')""",
    }
    rows = []
    for env in ENVS:
        for label, sql in sort_conditions.items():
            rows.append((env, label, one(env, "hexin_wms", sql)))
    checks.append(("2026-08-31 sync_picking_status_after_sort", rows))

    # 8 cancel status
    rows = []
    for env in ENVS:
        rows.append((env, "detail not CANCELLED", one(env, "hexin_wms",
            """select count(*) from wms_picking_detail d join wms_picking_order o
               on o.del_flag='0' and d.del_flag='0' and d.picking_order_no=o.picking_order_no
               where o.picking_status='CANCELLED' and coalesce(d.picking_status,'') is distinct from 'CANCELLED'""")))
        rows.append((env, "sub not CANCELLED", one(env, "hexin_wms",
            """select count(*) from wms_picking_sub_order s join wms_picking_order o
               on o.del_flag='0' and s.del_flag='0' and s.picking_order_no=o.picking_order_no
               where o.picking_status='CANCELLED' and coalesce(s.picking_status,'') is distinct from 'CANCELLED'""")))
    checks.append(("2026-08-31 sync_picking_status_after_cancel", rows))

    # 9 warehouse area dispatch
    rows = []
    for env in ENVS:
        rows.append((env, "old_codes_1_2", one(env, "hexin_masterdata",
            "select count(*) from md_warehouse_area where cast(dispatch_status as varchar) in ('1','2')")))
        rows.append((env, "Y_N_counts", q(env, "hexin_masterdata",
            "select dispatch_status, count(*) from md_warehouse_area group by dispatch_status order by 1")))
    checks.append(("2026-09-03 fix_warehouse_area_dispatch_status", rows))

    # 10 work stage backfill
    rows = []
    for env in ENVS:
        rows.append((env, "work_stage_null_remaining", one(env, "hexin_wms",
            """select count(*) from wms_picking_order
               where del_flag='0' and (work_stage is null or btrim(work_stage)='')
                 and (qc_order_no is null or btrim(qc_order_no)='')
                 and (biz_source is null or btrim(biz_source)='' or btrim(biz_source)='OUTBOUND')""")))
        rows.append((env, "work_stage_filled", one(env, "hexin_wms",
            "select count(*) from wms_picking_order where del_flag='0' and work_stage is not null and btrim(work_stage)<>''")))
    checks.append(("2026-09-11 picking_order_work_stage_backfill", rows))

    # 11 logistics group ids
    rows = []
    for env in ENVS:
        for table in ["wms_picking_plan", "wms_first_leg_box", "wms_first_leg_group_order"]:
            rows.append((env, f"{table} remaining", one(env, "hexin_wms",
                f"select count(*) from {table} where logistics_group_id is not null and (logistics_group_ids is null or cardinality(logistics_group_ids)=0)")))
            rows.append((env, f"{table} filled", one(env, "hexin_wms",
                f"select count(*) from {table} where logistics_group_ids is not null and cardinality(logistics_group_ids)>0")))
    checks.append(("2026-08-27 migrate_logistics_group_ids", rows))

    for label, items in checks:
        print(f"\n===== {label}")
        for item in items:
            print("  ", item)


if __name__ == "__main__":
    main()
