"""按数据库现状把一张未完成的单从断点续跑到 UPLOADED（幂等）。"""

from __future__ import annotations

import sys

import chain
from hexin_client import HexinClient
from probe_step import fetch_all


def build_ctx(external_no: str) -> dict:
    rows = fetch_all(
        "hexin_oms",
        "select id, order_no from oms_order where external_order_no=%s and del_flag='0'",
        (external_no,),
    )
    if not rows:
        raise SystemExit(f"订单不存在: {external_no}")
    ctx = {"external_no": external_no, "order_id": rows[0][0], "order_no": rows[0][1]}
    pkgs = fetch_all(
        "hexin_oms",
        "select id, package_no, logistics_type_id from oms_package "
        "where order_id=%s and del_flag='0'",
        (ctx["order_id"],),
    )
    ctx["packages"] = [
        {"id": pid, "package_no": pno, "logistics_type_id": ltid}
        for pid, pno, ltid in pkgs
    ]
    for pkg in ctx["packages"]:
        out = fetch_all(
            "hexin_wms",
            "select out_no from wms_order_out where relation_no=%s and del_flag='0'",
            (pkg["package_no"],),
        )
        if out:
            pkg["out_no"] = out[0][0]
    plan_ids = chain._plan_ids(ctx) if ctx["packages"] else []
    picking_nos, delivery_nos = [], []
    for plan_id in plan_ids:
        row = fetch_all(
            "hexin_wms",
            "select picking_order_no, delivery_no from wms_picking_plan where id=%s",
            (plan_id,),
        )[0]
        if row[0]:
            picking_nos.append(row[0])
        if row[1]:
            delivery_nos.append(row[1])
    ctx["picking_order_nos"] = sorted(set(picking_nos))
    ctx["delivery_nos"] = sorted(set(delivery_nos))
    ctx["_plan_ids"] = plan_ids
    return ctx


def main(external_no: str) -> None:
    client = HexinClient()
    ctx = build_ctx(external_no)
    print("现状:", {k: v for k, v in ctx.items() if k != "packages"}, "packages=", ctx["packages"])

    if not ctx["packages"]:
        chain.approve_order(client, ctx)
        ctx["packages"] = chain.wait_packages(ctx)

    if any(p.get("logistics_type_id") is None for p in ctx["packages"]):
        chain.select_logistics(client, ctx)

    if any(not p.get("out_no") for p in ctx["packages"]):
        chain.transfer(client, ctx)

    plans = fetch_all(
        "hexin_wms",
        "select id, outbound_order_no, picking_order_no, delivery_no from wms_picking_plan "
        "where outbound_order_no = any(%s) and del_flag='0'",
        ([p["out_no"] for p in ctx["packages"]],),
    )
    print("拣货计划:", plans)

    if any(not row[2] for row in plans):
        chain.bind_and_print(client, ctx)

    picked = fetch_all(
        "hexin_wms",
        "select out_status from wms_order_out where out_no = any(%s)",
        ([p["out_no"] for p in ctx["packages"]],),
    )
    if any(row[0] == "PICKING" for row in picked):
        chain.complete_pick(client, ctx)

    statuses = fetch_all(
        "hexin_wms",
        "select out_status from wms_order_out where out_no = any(%s)",
        ([p["out_no"] for p in ctx["packages"]],),
    )
    print("出库单状态:", statuses)

    if any(row[0] == "WAIT_CHECK" for row in statuses):
        chain.scan_and_check(client, ctx)

    plans_after = fetch_all(
        "hexin_wms",
        "select delivery_no from wms_picking_plan where outbound_order_no = any(%s) and del_flag='0'",
        ([p["out_no"] for p in ctx["packages"]],),
    )
    if any(not row[0] for row in plans_after):
        chain.generate_delivery(client, ctx)

    delivery = fetch_all(
        "hexin_wms",
        "select d.id, d.delivery_no, d.delivery_status from wms_delivery_order d "
        "join wms_picking_plan p on p.delivery_no=d.delivery_no "
        "where p.outbound_order_no = any(%s) and d.del_flag='0'",
        ([p["out_no"] for p in ctx["packages"]],),
    )
    print("提货单:", delivery)
    if delivery and any(row[2] == "PICKABLE" for row in delivery):
        chain.generate_delivery(client, ctx)
        delivery = fetch_all(
            "hexin_wms",
            "select d.id, d.delivery_no, d.delivery_status from wms_delivery_order d "
            "where d.delivery_no = any(%s) and d.del_flag='0'",
            (ctx["delivery_nos"],),
        )
        print("生成后:", delivery)
    if delivery and any(row[2] == "WAIT_UPLOAD" for row in delivery):
        ctx["delivery_nos"] = [row[1] for row in delivery]
        chain.upload(client, ctx)

    final = fetch_all(
        "hexin_wms",
        "select d.id, d.delivery_no, d.delivery_status from wms_delivery_order d "
        "join wms_picking_plan p on p.delivery_no=d.delivery_no "
        "where p.outbound_order_no = any(%s) and d.del_flag='0'",
        ([p["out_no"] for p in ctx["packages"]],),
    )
    print("最终:", final)


if __name__ == "__main__":
    main(sys.argv[1])
