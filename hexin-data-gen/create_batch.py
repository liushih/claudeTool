"""造一批同 pack_batch_no 的 B2D 待发货数据：两单 -> 核单装箱 -> 装箱/封箱/转待发货。"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime

import hexin_client
from probe_step import (
    fetch_all, save_state, step_approve, step_bindpicker, step_create,
    step_pick, step_printadvance, step_setlogistics, step_transfer,
)

hexin_client.BASE_URL = "http://localhost/dev-api"


def wait_packages(order_id: int) -> list[tuple[int, str]]:
    for _ in range(15):
        rows = fetch_all(
            "hexin_oms",
            "select id, package_no from oms_package where order_id=%s and del_flag='0'",
            (order_id,),
        )
        if rows:
            return [(r[0], r[1]) for r in rows]
        time.sleep(2)
    raise SystemExit(f"订单 {order_id} 未生成包裹")


def build_one(client, tag: str) -> dict:
    state: dict = {}
    print(f"\n===== 造单 {tag} =====")
    state = step_create(client, state)
    state = step_approve(client, state)
    pkgs = wait_packages(state["order_id"])
    state["package_ids"] = [p[0] for p in pkgs]
    state["package_no"] = pkgs[0][1]
    save_state(state)
    state = step_setlogistics(client, state)
    state = step_transfer(client, state)
    rows = fetch_all(
        "hexin_wms",
        "select out_no from wms_order_out where relation_no=%s and del_flag='0'",
        (state["package_no"],),
    )
    state["out_no"] = rows[0][0] if rows else None
    state = step_bindpicker(client, state)
    state = step_printadvance(client, state)
    state = step_pick(client, state)
    plans = fetch_all(
        "hexin_wms",
        "select p.id, p.outbound_order_no, o.out_status, p.packing_status "
        "from wms_picking_plan p join wms_order_out o on o.out_no=p.outbound_order_no and o.del_flag='0' "
        "where p.outbound_order_no=%s and p.del_flag='0'",
        (state["out_no"],),
    )
    print("plan:", plans)
    state["plan_id"] = plans[0][0]
    state["plan_status"] = plans[0][2]
    state["packing_status"] = plans[0][3]
    return state


def packing_details(out_nos: list[str]) -> list[dict]:
    rows = fetch_all(
        "hexin_wms",
        "select outbound_order_no, picking_sku, operation_qty from wms_picking_detail "
        "where outbound_order_no = any(%s) and del_flag='0'",
        (out_nos,),
    )
    return [
        {"outboundOrderNo": out_no, "skuCode": sku, "qty": int(qty)}
        for out_no, sku, qty in rows
    ]


def main() -> None:
    client = hexin_client.HexinClient()
    client.login()
    a = build_one(client, "A")
    b = build_one(client, "B")
    plan_ids = [a["plan_id"], b["plan_id"]]
    out_nos = [a["out_no"], b["out_no"]]
    print("plan_ids =", plan_ids, "out_nos =", out_nos)

    res = client.post("/wms/b2dPacking/start", {"planIds": plan_ids})
    print("[start]", res.code, res.msg)

    specs = fetch_all("hexin_wms", "select id, spec_name from wms_box_spec where del_flag='0' limit 5")
    print("box specs:", specs)
    spec_id = specs[0][0] if specs else None

    suffix = "T" + datetime.now().strftime("%H%M%S")
    items = packing_details(out_nos)
    res = client.post(
        "/wms/b2dPacking/createBox",
        {"planIds": plan_ids, "boxSpecId": spec_id, "boxNoSuffix": suffix,
         "weightKg": 1, "items": items},
    )
    print("[createBox]", res.code, res.msg)

    res = client.post("/wms/b2dPacking/seal", {"planIds": plan_ids})
    print("[seal]", res.code, res.msg)

    res = client.post("/wms/b2dPacking/transferPendingShip/preview", {"planIds": plan_ids})
    print("[transfer preview]", res.code, res.msg, json.dumps(res.data, ensure_ascii=False)[:300])

    res = client.post("/wms/b2dPacking/transferPendingShip/confirm", {"planIds": plan_ids})
    print("[transfer confirm]", res.code, res.msg, json.dumps(res.data, ensure_ascii=False)[:300])

    rows = fetch_all(
        "hexin_wms",
        "select p.id, p.outbound_order_no, o.pack_batch_no, o.out_status, p.packing_status "
        "from wms_picking_plan p join wms_order_out o on o.out_no=p.outbound_order_no and o.del_flag='0' "
        "where p.id = any(%s) and p.del_flag='0'",
        (plan_ids,),
    )
    print("RESULT:")
    for r in rows:
        print("  ", r)


if __name__ == "__main__":
    sys.exit(main())
