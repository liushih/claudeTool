"""C7 场景造数（可复现版）：两单同批、各装一箱，只给 A 生成提货单。"""

from __future__ import annotations

import json
import random
import sys
import time

import hexin_client
from probe_step import (
    PROBE_PNG, fetch_all, save_state, step_approve, step_bindpicker,
    step_create, step_pick, step_printadvance, step_setlogistics, step_transfer,
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
        "select p.id from wms_picking_plan p join wms_order_out o on o.out_no=p.outbound_order_no "
        "and o.del_flag='0' where p.outbound_order_no=%s and p.del_flag='0'",
        (state["out_no"],),
    )
    state["plan_id"] = plans[0][0]
    print("plan:", state["plan_id"], state["out_no"])
    return state


def box_items(out_no: str) -> list[dict]:
    return [
        {"outboundOrderNo": out_no, "skuCode": sku, "qty": int(qty)}
        for out_no, sku, qty in fetch_all(
            "hexin_wms",
            "select outbound_order_no,picking_sku,operation_qty from wms_picking_detail "
            "where outbound_order_no=%s and del_flag='0'",
            (out_no,),
        )
    ]


def create_box(client, plan_ids, spec_id, out_no) -> None:
    for _ in range(10):
        suffix = str(random.randint(100, 999))
        r = client.post("/wms/b2dPacking/createBox", {
            "planIds": plan_ids, "boxSpecId": spec_id, "boxNoSuffix": suffix,
            "weightKg": 1, "items": box_items(out_no),
        })
        print(f"[createBox {out_no} {suffix}]", r.code, r.msg)
        if r.ok:
            return
    raise SystemExit("createBox 失败")


def main() -> None:
    client = hexin_client.HexinClient()
    client.login()
    a = build_one(client, "A")
    b = build_one(client, "B")
    plan_ids = [a["plan_id"], b["plan_id"]]

    print("[start]", client.post("/wms/b2dPacking/start", {"planIds": plan_ids}).msg)
    spec = fetch_all("hexin_wms", "select id from wms_box_spec where del_flag='0' limit 1")[0][0]
    create_box(client, plan_ids, spec, a["out_no"])
    create_box(client, plan_ids, spec, b["out_no"])
    print("[seal]", client.post("/wms/b2dPacking/seal", {"planIds": plan_ids}).msg)
    r = client.post("/wms/b2dPacking/transferPendingShip/confirm", {"planIds": plan_ids})
    print("[transfer]", r.code, r.msg, json.dumps(r.data, ensure_ascii=False)[:160])

    r = client.post("/wms/pickingPlan/delivery/generate/confirm", {"planIds": [a["plan_id"]]})
    print("[gen delivery A only]", r.code, r.msg, r.data)
    delivery_nos = r.data or []
    if delivery_nos:
        ids = fetch_all(
            "hexin_wms",
            "select id from wms_delivery_order where delivery_no=any(%s) and del_flag='0'",
            (delivery_nos,),
        )
        for (did,) in ids:
            up = client.post_multipart(
                "/wms/deliveryOrder/uploadAttachment",
                files={"file": ("probe.png", PROBE_PNG, "image/png")},
                params={"deliveryOrderId": did},
            )
            print("[upload]", did, up.code, up.msg)

    rows = fetch_all(
        "hexin_wms",
        "select p.id,p.outbound_order_no,p.delivery_no,o.pack_batch_no,o.out_status "
        "from wms_picking_plan p join wms_order_out o on o.out_no=p.outbound_order_no "
        "and o.del_flag='0' where p.id=any(%s) order by p.id",
        (plan_ids,),
    )
    print("RESULT:")
    for row in rows:
        print("  ", row)


if __name__ == "__main__":
    sys.exit(main())
