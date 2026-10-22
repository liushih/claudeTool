"""只读：列出厦门普货仓(565) 标准库区、正常库位上有充足库存的 SKU 候选。"""

from __future__ import annotations

from probe_step import db_connect

WAREHOUSE_ID = 565
MIN_AVAILABLE = 500


def main() -> None:
    with db_connect("hexin_masterdata") as conn, conn.cursor() as cur:
        cur.execute(
            "select id, area_code, warehouse_area_name, area_type, is_hot "
            "from md_warehouse_area where warehouse_id=%s and del_flag='0' and area_type='standard'",
            (WAREHOUSE_ID,),
        )
        areas = {row[0]: row for row in cur.fetchall()}
        area_ids = list(areas)
        cur.execute(
            "select id, warehouse_area_id, position_name, type, use_state "
            "from md_warehouse_position "
            "where warehouse_id=%s and del_flag='0' and warehouse_area_id = any(%s) "
            "and coalesce(type,'') not in ('defective','scrap','front_scrap') "
            "and coalesce(use_state,'') <> 'disabled'",
            (WAREHOUSE_ID, area_ids),
        )
        positions = {row[0]: row for row in cur.fetchall()}

    if not positions:
        print("没有正常库位")
        return

    with db_connect("hexin_wms") as conn, conn.cursor() as cur:
        cur.execute(
            "select sku_id, sku, sku_name, location_id, zone_id, "
            "sum(qty_available) available, max(sales_status) sales_status "
            "from wms_inventory_summary "
            "where del_flag='0' and warehouse_id=%s and location_id = any(%s) "
            "group by sku_id, sku, sku_name, location_id, zone_id "
            "having sum(qty_available) >= %s "
            "order by available desc",
            (WAREHOUSE_ID, list(positions), MIN_AVAILABLE),
        )
        rows = cur.fetchall()

    print(f"标准库区数={len(areas)}  正常库位数={len(positions)}  命中={len(rows)}\n")
    header = f"{'sku_id':>8} {'sku':<28} {'名称':<14} {'可用':>10} {'库区':<18} {'库位':<16} {'热区':<12} 销售状态"
    print(header)
    print("-" * len(header))
    for sku_id, sku, name, location_id, zone_id, available, sales_status in rows[:30]:
        area = areas.get(zone_id, (None, "", "", "", ""))
        pos = positions.get(location_id, (None, None, "", "", ""))
        print(f"{sku_id:>8} {sku:<28} {name or '':<14} {available:>10.0f} "
              f"{area[2]:<18} {pos[2]:<16} {str(area[4]):<12} {sales_status}")


if __name__ == "__main__":
    main()
