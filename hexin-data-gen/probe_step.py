"""分步探针：create → approve → genpkg → transfer → pick → check → gendelivery → upload。

状态存在 state.json，可重复执行单步，便于逐步排错。
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

import psycopg

from hexin_client import BASE_URL, HexinClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hxpaths import DB_ENV_FILE  # noqa: E402

WAREHOUSE_ID = 565
STORE_ID = 19266
STORE_CODE = "B2D-ALI-004-LB"
PLATFORM_ID = 17
SKU_ID = 333018
SKU = "SY220002-GY1-4XL-2"
SKU_NAME = "塑身连衣裙"
LOGISTICS_TYPE_ID = 13  # 兜底值，实际由页面同款匹配接口决定
LOGISTICS_METHOD = "DHL快递-604083014-20kg以上"
PICKING_STRATEGY_ID = 874827230561214544   # B2D-shop（物理仓 71 = 厦门普货仓）
PICKER_USER_ID = 1                          # admin

STATE_FILE = Path(__file__).with_name("state.json")


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def db_connect(dbname: str):
    values = {}
    for line in DB_ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        values[key.strip()] = val.strip()
    return psycopg.connect(
        host=values["DEV_HOST"], port=values["DEV_PORT"], user=values["DEV_USER"],
        password=values["DEV_PASSWORD"], dbname=dbname,
        options="-c default_transaction_read_only=on", connect_timeout=10,
    )


def fetch_all(dbname: str, sql: str, params: tuple = ()):
    last = None
    for attempt in range(3):
        try:
            with db_connect(dbname) as conn, conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchall()
        except psycopg.OperationalError as exc:   # Windows 端口耗尽 / 连接抖动
            last = exc
            time.sleep(1 + attempt)
    raise last


def show(label: str, result) -> None:
    body = json.dumps(result.data, ensure_ascii=False) if hasattr(result, "data") else str(result)
    if len(body) > 800:
        body = body[:800] + "..."
    print(f"[{label}] code={result.code} msg={result.msg} data={body}")


def step_create(client: HexinClient, state: dict) -> dict:
    external_no = "PROBE-" + datetime.now().strftime("%Y%m%d%H%M%S")
    draft_id = str(uuid.uuid4())

    item = {
        "sysSkuId": SKU_ID, "sysSku": SKU, "sysSkuName": SKU_NAME,
        "orderQty": 1, "unitPriceExclTax": 10, "unitWeight": 0.2,
    }
    res = client.post("/oms/manualOrder/item-stage/items", [item], params={"clientDraftId": draft_id})
    show("append", res)
    if not res.ok:
        raise SystemExit(1)

    res = client.get("/oms/manualOrder/item-stage/summary", {"clientDraftId": draft_id})
    show("summary", res)
    stage_token = (res.data or {}).get("stageToken")
    if not stage_token:
        raise SystemExit("未拿到 stageToken")

    body = {
        "basicInfo": {
            "manualOrderSource": "customer_order", "platformId": PLATFORM_ID,
            "storeCode": STORE_CODE, "storeId": STORE_ID,
            "externalOrderNo": external_no, "platformCurrency": "USD",
            "orderSalesman": "admin", "orderRemark": "probe data",
        },
        "customerInfo": {
            "receiverName": "Probe Buyer", "buyerName": "Probe Buyer",
            "receiverPhone": "13800138000", "receiverEmail": "probe@example.com",
            "countryName": "United States", "countryCode": "US",
            "provinceName": "California", "provinceCode": "CA",
            "cityName": "Los Angeles", "postCode": "90001",
            "addressLines": "123 Main St",
        },
        "paymentInfo": {
            "settlementMethod": "immediate_pay", "totalAmount": 10,
            "freightAmount": 0, "goodsTotalTax": 0,
            "lines": [{"lineNo": 1, "payMethod": "bank_transfer", "paidAmount": 10,
                       "payCurrency": "USD", "payRatio": 100}],
        },
        "clientDraftId": draft_id,
        "stageToken": stage_token,
    }
    res = client.post("/oms/manualOrder", body)
    show("create", res)
    if not res.ok:
        raise SystemExit(1)

    for _ in range(20):
        time.sleep(2)
        rows = fetch_all("hexin_oms",
                         "select id, order_no, order_status from oms_order where external_order_no=%s and del_flag='0'",
                         (external_no,))
        if rows:
            state.update({"external_no": external_no, "order_id": rows[0][0],
                          "order_no": rows[0][1], "order_status": rows[0][2]})
            save_state(state)
            print(f"order_id={rows[0][0]} order_no={rows[0][1]} status={rows[0][2]}")
            return state
    raise SystemExit("订单未落库")


def step_approve(client: HexinClient, state: dict) -> dict:
    res = client.post(f"/oms/manualOrder/{state['order_id']}/submitApproval")
    show("submitApproval", res)
    if not res.ok:
        raise SystemExit(1)
    res = client.post("/oms/manualOrder/approve", {"id": state["order_id"], "passFlag": True})
    show("approve", res)
    if not res.ok:
        raise SystemExit(1)
    rows = fetch_all("hexin_oms", "select order_status from oms_order where id=%s", (state["order_id"],))
    state["order_status"] = rows[0][0]
    save_state(state)
    print("order_status =", state["order_status"])
    return state


def step_genpkg(client: HexinClient, state: dict) -> dict:
    items = fetch_all("hexin_oms",
                      "select id, sys_sku, order_qty, pending_ship_qty from oms_order_item where order_id=%s and del_flag='0'",
                      (state["order_id"],))
    print("order items:", items)
    packages = [[{"orderItemId": row[0], "planShipQty": int(row[3] or row[2])}] for row in items]
    res = client.post("/oms/order/generatePackage",
                      {"orderId": state["order_id"], "packages": packages, "warehouseId": WAREHOUSE_ID})
    show("generatePackage", res)
    if not res.ok:
        raise SystemExit(1)
    state["package_ids"] = res.data
    save_state(state)
    print("package_ids =", res.data)
    return state


def wait_package_ready(package_id: int) -> None:
    """包裹由政策引擎异步落库，报关模式没写完时选物流方式会报「报关模式不能为空」。"""
    for _ in range(15):
        rows = fetch_all("hexin_oms",
                         "select customs_mode from oms_package where id=%s", (package_id,))
        if rows and rows[0][0]:
            return
        time.sleep(2)
    raise SystemExit(f"包裹 {package_id} 报关模式一直为空")


def resolve_b2d_logistics(client: HexinClient, package_id: int) -> dict:
    """走页面同款匹配接口（/masterdata/logisticsType/match），取第一条 B2D。"""
    row = fetch_all(
        "hexin_oms",
        "select warehouse_id, customs_mode, platform_id, country_code, store_id, revenue_company_id "
        "from oms_package where id=%s",
        (package_id,),
    )[0]
    warehouse_id, customs, platform_id, country, store_id, company_id = row
    attrs_rows = fetch_all(
        "hexin_oms",
        "select distinct sys_sku_logistics_attr from oms_package_sku where package_id=%s",
        (package_id,),
    )
    attrs = ",".join(sorted({a.strip() for (a,) in attrs_rows if a and a.strip()}))
    params = {
        "warehouseId": str(warehouse_id),
        "customsClearanceModel": customs,
        "sysSkuLogisticsAttrs": attrs,
        "platformId": str(platform_id),
        "countryCode": country,
        "storeId": str(store_id),
        "revenueCompanyId": str(company_id),
        "pageNum": 1,
        "pageSize": 200,
    }
    resp = client.session.get(
        f"{BASE_URL}/masterdata/logisticsType/match",
        params=params, headers=client._headers(), timeout=60,
    )
    rows = resp.json().get("rows") or []
    b2d = [r for r in rows if str(r.get("isB2d", "")).upper() == "Y"]
    print(f"匹配到 {len(rows)} 个物流方式，其中 B2D {len(b2d)} 个")
    if not b2d:
        raise SystemExit("匹配结果里没有 B2D 物流方式")
    for item in b2d[:5]:
        print(f"  候选: {item['id']} {item['typeName']}")
    return b2d[0]


def step_setlogistics(client: HexinClient, state: dict) -> dict:
    """按页面同款匹配规则选 B2D 物流方式（不再硬编码 id）。"""
    for package_id in state["package_ids"]:
        wait_package_ready(package_id)
        target = resolve_b2d_logistics(client, package_id)
        res = client.post(
            "/oms/package/selectLogisticsMethod",
            {
                "id": package_id,
                "logisticsTypeId": target["id"],
                "logisticsMethod": target["typeName"],
                "fetchTrackingNo": False,
            },
        )
        show(f"selectLogisticsMethod({package_id})", res)
        if not res.ok:
            raise SystemExit(1)
    rows = fetch_all("hexin_oms",
                     "select id, logistics_type_id, carrier_name, tracking_no from oms_package where id = any(%s)",
                     (state["package_ids"],))
    print("packages after update:", rows)
    state["logistics_type_id"] = rows[0][1] if rows else None
    save_state(state)
    return state


def step_transfer(client: HexinClient, state: dict) -> dict:
    res = client.post("/oms/package/batchTransferWarehouse", state["package_ids"])
    show("batchTransferWarehouse", res)
    if not res.ok:
        raise SystemExit(1)
    return state


def step_inspect(state: dict) -> dict:
    oms = fetch_all("hexin_oms",
                    "select id, package_no, pkg_status from oms_package where order_id=%s and del_flag='0'",
                    (state["order_id"],))
    print("packages:", oms)
    wms = fetch_all("hexin_wms",
                    "select id, out_no, out_status, shipping_mode, logistics_type_id, carrier_name, company_id "
                    "from wms_order_out where relation_no in (select package_no from oms_package where order_id=%s) and del_flag='0'",
                    (state["order_id"],))
    print("order_out:", wms)
    plans = fetch_all("hexin_wms",
                      "select id, outbound_order_no, delivery_no, picking_status, work_stage, shipping_mode, cart_no "
                      "from wms_picking_plan where outbound_order_no in "
                      "(select out_no from wms_order_out where relation_no in "
                      "(select package_no from oms_package where order_id=%s)) and del_flag='0'",
                      (state["order_id"],))
    print("picking_plan:", plans)
    return state


def step_pickstrategy(client: HexinClient, state: dict) -> dict:
    plan_ids = fetch_all(
        "hexin_wms",
        "select id from wms_picking_plan where outbound_order_no in "
        "(select out_no from wms_order_out where relation_no=%s) and del_flag='0'",
        (state["package_no"],),
    )
    plan_ids = [row[0] for row in plan_ids]
    print("plan_ids =", plan_ids)
    res = client.post(
        "/wms/pickingStrategy/execute",
        {
            "strategyIds": [PICKING_STRATEGY_ID],
            "outboundType": "B2D",
            "query": {"planIds": plan_ids},
        },
    )
    show("executeStrategy", res)
    if not res.ok:
        raise SystemExit(1)
    return state


def plan_ids_of(state: dict) -> list[int]:
    rows = fetch_all(
        "hexin_wms",
        "select id from wms_picking_plan where outbound_order_no in "
        "(select out_no from wms_order_out where relation_no=%s) and del_flag='0'",
        (state["package_no"],),
    )
    return [row[0] for row in rows]


def step_bindpicker(client: HexinClient, state: dict) -> dict:
    res = client.post(
        "/wms/pickingPlan/bindPicker",
        {"planIds": plan_ids_of(state), "bindTargetPicker": PICKER_USER_ID, "bindWaitPickOnly": True},
    )
    show("bindPicker", res)
    if not res.ok:
        raise SystemExit(1)
    return state


def step_printadvance(client: HexinClient, state: dict) -> dict:
    plan_ids = plan_ids_of(state)
    rows = fetch_all(
        "hexin_wms",
        "select picking_group, warehouse_id, picker from wms_picking_plan where id=%s",
        (plan_ids[0],),
    )
    picking_group, warehouse_id, picker = rows[0]
    res = client.post(
        "/wms/pickingPlan/printAdvance",
        {
            "planIds": plan_ids,
            "pickingGroup": picking_group,
            "warehouseId": warehouse_id,
            "picker": picker,
            "pickingPrintType": "picking",
            "pickingPrintTime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "pickingPrintMethod": "piece_picking",
        },
    )
    show("printAdvance", res)
    if not res.ok:
        raise SystemExit(1)
    state["picking_order_no"] = res.data
    save_state(state)
    print("picking_order_no =", res.data)
    return state


def step_pick(client: HexinClient, state: dict) -> dict:
    picking_order_no = state["picking_order_no"]["pickingOrderNo"]
    rows = fetch_all("hexin_wms",
                     "select outbound_order_no, picking_sku, operation_qty, inventory_id, loc_id "
                     "from wms_picking_detail where picking_order_no=%s and del_flag='0'",
                     (picking_order_no,))
    details = [
        {
            "outboundOrderNo": out_no,
            "pickingSku": sku,
            "operationQty": int(qty),
            "inventoryId": inventory_id,
            "locId": loc_id,
        }
        for out_no, sku, qty, inventory_id, loc_id in rows
    ]
    res = client.post(
        "/wms/pickList/completePick",
        {"orders": [{"pickingOrderNo": picking_order_no, "details": details}]},
    )
    show("completePick", res)
    if not res.ok:
        raise SystemExit(1)
    return state


def step_scan(client: HexinClient, state: dict) -> dict:
    res = client.post(
        "/wms/checkTask/scanPackage",
        {
            "packageNo": state["package_no"],
            "warehouseId": WAREHOUSE_ID,
            "logisticsTypeId": state.get("logistics_type_id"),
        },
    )
    show("scanPackage", res)
    if not res.ok:
        raise SystemExit(1)
    return state


def step_check(client: HexinClient, state: dict) -> dict:
    res = client.post(
        "/wms/checkTask/submitWeight/package",
        {"packageNo": state["package_no"], "ckWeight": 1, "outboundOrderNo": state["out_no"]},
    )
    show("submitWeight", res)
    if not res.ok:
        raise SystemExit(1)
    return state


def step_gendelivery(client: HexinClient, state: dict) -> dict:
    res = client.post("/wms/pickingPlan/delivery/generate/confirm", {"planIds": plan_ids_of(state)})
    show("generateDelivery", res)
    if not res.ok:
        raise SystemExit(1)
    delivery_nos = res.data or []
    state["delivery_nos"] = delivery_nos
    save_state(state)
    print("delivery_nos =", delivery_nos)
    return state


def delivery_order_ids(delivery_nos: list[str]) -> list[int]:
    if not delivery_nos:
        return []
    rows = fetch_all(
        "hexin_wms",
        "select id, delivery_no, delivery_status from wms_delivery_order "
        "where delivery_no = any(%s) and del_flag='0'",
        (delivery_nos,),
    )
    print("delivery orders:", rows)
    return [row[0] for row in rows]


PROBE_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05"
    b"\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def step_upload(client: HexinClient, state: dict) -> dict:
    ids = delivery_order_ids(state["delivery_nos"])
    if not ids:
        raise SystemExit("未找到提货单")
    for delivery_id in ids:
        res = client.post_multipart(
            "/wms/deliveryOrder/uploadAttachment",
            files={"file": ("probe.png", PROBE_PNG, "image/png")},
            params={"deliveryOrderId": delivery_id},
        )
        show(f"uploadAttachment({delivery_id})", res)
        if not res.ok:
            raise SystemExit(1)
    rows = fetch_all(
        "hexin_wms",
        "select id, delivery_no, delivery_status from wms_delivery_order where id = any(%s)",
        (ids,),
    )
    print("delivery orders after upload:", rows)
    return state


def step_runall(client: HexinClient, state: dict) -> dict:
    state = step_create(client, state)
    state = step_approve(client, state)
    # 政策引擎通常自动建包；没有则显式生成
    rows = []
    for _ in range(5):
        rows = fetch_all("hexin_oms",
                         "select id, package_no from oms_package where order_id=%s and del_flag='0'",
                         (state["order_id"],))
        if rows:
            break
        time.sleep(2)
    if not rows:
        state = step_genpkg(client, state)
        rows = fetch_all("hexin_oms",
                         "select id, package_no from oms_package where order_id=%s and del_flag='0'",
                         (state["order_id"],))
    state["package_ids"] = [row[0] for row in rows]
    state["package_no"] = rows[0][1] if rows else None
    save_state(state)
    print("packages:", rows)
    state = step_setlogistics(client, state)
    state = step_transfer(client, state)
    rows = fetch_all("hexin_wms",
                     "select out_no from wms_order_out where relation_no=%s and del_flag='0'",
                     (state["package_no"],))
    state["out_no"] = rows[0][0] if rows else None
    save_state(state)
    print("out_no =", state["out_no"])
    state = step_bindpicker(client, state)
    state = step_printadvance(client, state)
    state = step_pick(client, state)
    state = step_scan(client, state)
    state = step_check(client, state)
    state = step_gendelivery(client, state)
    state = step_upload(client, state)
    print("\n探针完成")
    return state


STEPS = {
    "create": step_create,
    "approve": step_approve,
    "genpkg": step_genpkg,
    "setlogistics": step_setlogistics,
    "transfer": step_transfer,
    "bindpicker": step_bindpicker,
    "printadvance": step_printadvance,
    "pick": step_pick,
    "scan": step_scan,
    "check": step_check,
    "gendelivery": step_gendelivery,
    "upload": step_upload,
    "runall": step_runall,
    "pickstrategy": step_pickstrategy,
}

if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else "create"
    state = load_state()
    client = HexinClient()
    if step == "inspect":
        step_inspect(state)
    elif step in STEPS:
        STEPS[step](client, state)
    else:
        raise SystemExit(f"未知步骤: {step}")
