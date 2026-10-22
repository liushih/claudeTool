"""单张提货单的业务链路（无文件副作用），供批量执行器调用。

链路：建单 → 提交审批 → 审批 → 选 B2D 物流 → 转仓 → 绑定拣货员 → 打印推进
      → 完成拣货 → 扫描认领 → 核单称重 → 生成提货单 → 上传附件(UPLOADED)
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime

from hexin_client import BASE_URL, HexinClient
from probe_step import (
    PROBE_PNG,
    SKU,
    SKU_ID,
    SKU_NAME,
    STORE_CODE,
    STORE_ID,
    PLATFORM_ID,
    WAREHOUSE_ID,
    PICKER_USER_ID,
    fetch_all,
    show,
)


class ChainError(RuntimeError):
    def __init__(self, stage: str, message: str):
        super().__init__(f"[{stage}] {message}")
        self.stage = stage


def _post(client: HexinClient, stage: str, path: str, body=None, params=None):
    res = client.post(path, body, params=params)
    if not res.ok:
        raise ChainError(stage, res.msg or f"HTTP {res.code}")
    return res


def _get(client: HexinClient, stage: str, path: str, params=None):
    res = client.get(path, params)
    if not res.ok:
        raise ChainError(stage, res.msg or f"HTTP {res.code}")
    return res


def create_order(client: HexinClient, external_no: str) -> dict:
    draft_id = str(uuid.uuid4())
    item = {
        "sysSkuId": SKU_ID, "sysSku": SKU, "sysSkuName": SKU_NAME,
        "orderQty": 1, "unitPriceExclTax": 10, "unitWeight": 0.2,
    }
    _post(client, "create", "/oms/manualOrder/item-stage/items", [item],
          params={"clientDraftId": draft_id})
    summary = _get(client, "create", "/oms/manualOrder/item-stage/summary",
                   {"clientDraftId": draft_id})
    stage_token = (summary.data or {}).get("stageToken")
    if not stage_token:
        raise ChainError("create", "未拿到 stageToken")

    body = {
        "basicInfo": {
            "manualOrderSource": "customer_order", "platformId": PLATFORM_ID,
            "storeCode": STORE_CODE, "storeId": STORE_ID,
            "externalOrderNo": external_no, "platformCurrency": "USD",
            "orderSalesman": "admin", "orderRemark": "batch data",
        },
        "customerInfo": {
            "receiverName": "Batch Buyer", "buyerName": "Batch Buyer",
            "receiverPhone": "13800138000", "receiverEmail": "batch@example.com",
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
    _post(client, "create", "/oms/manualOrder", body)

    for _ in range(20):
        time.sleep(1.5)
        rows = fetch_all(
            "hexin_oms",
            "select id, order_no, order_status from oms_order "
            "where external_order_no=%s and del_flag='0'",
            (external_no,),
        )
        if rows:
            return {"external_no": external_no, "order_id": rows[0][0],
                    "order_no": rows[0][1], "order_status": rows[0][2]}
    raise ChainError("create", "订单 30 秒内未落库")


def approve_order(client: HexinClient, ctx: dict) -> None:
    _post(client, "approve", f"/oms/manualOrder/{ctx['order_id']}/submitApproval")
    _post(client, "approve", "/oms/manualOrder/approve",
          {"id": ctx["order_id"], "passFlag": True})


def wait_packages(ctx: dict, timeout: int = 30) -> list[dict]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        rows = fetch_all(
            "hexin_oms",
            "select id, package_no, customs_mode from oms_package "
            "where order_id=%s and del_flag='0'",
            (ctx["order_id"],),
        )
        if rows and all(row[2] for row in rows):
            return [{"id": row[0], "package_no": row[1]} for row in rows]
        time.sleep(2)
    raise ChainError("package", "包裹或报关模式未就绪")


def _resolve_b2d_logistics(client: HexinClient, package_id: int) -> dict:
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
        "warehouseId": str(warehouse_id), "customsClearanceModel": customs,
        "sysSkuLogisticsAttrs": attrs, "platformId": str(platform_id),
        "countryCode": country, "storeId": str(store_id),
        "revenueCompanyId": str(company_id), "pageNum": 1, "pageSize": 200,
    }
    resp = client.session.get(
        f"{BASE_URL}/masterdata/logisticsType/match",
        params=params, headers=client._headers(), timeout=60,
    )
    rows = resp.json().get("rows") or []
    b2d = [r for r in rows if str(r.get("isB2d", "")).upper() == "Y"]
    if not b2d:
        raise ChainError("logistics", f"匹配 {len(rows)} 个物流方式，无 B2D")
    return b2d[0]


def select_logistics(client: HexinClient, ctx: dict) -> None:
    for pkg in ctx["packages"]:
        target = _resolve_b2d_logistics(client, pkg["id"])
        _post(client, "logistics", "/oms/package/selectLogisticsMethod", {
            "id": pkg["id"],
            "logisticsTypeId": target["id"],
            "logisticsMethod": target["typeName"],
            "fetchTrackingNo": False,
        })
        pkg["logistics_type_id"] = target["id"]


def transfer(client: HexinClient, ctx: dict) -> None:
    ids = [pkg["id"] for pkg in ctx["packages"]]
    res = _post(client, "transfer", "/oms/package/batchTransferWarehouse", ids)
    data = res.data or {}
    if data.get("successCount", 0) < len(ids):
        raise ChainError("transfer", f"转仓失败: {data.get('failures')}")
    for pkg in ctx["packages"]:
        rows = fetch_all(
            "hexin_wms",
            "select out_no from wms_order_out where relation_no=%s and del_flag='0'",
            (pkg["package_no"],),
        )
        if not rows:
            raise ChainError("transfer", f"未生成出库单 {pkg['package_no']}")
        pkg["out_no"] = rows[0][0]


def _plan_ids(ctx: dict) -> list[int]:
    out_nos = [pkg["out_no"] for pkg in ctx["packages"] if pkg.get("out_no")]
    if not out_nos:
        return []
    rows = fetch_all(
        "hexin_wms",
        "select id from wms_picking_plan where outbound_order_no = any(%s) and del_flag='0'",
        (out_nos,),
    )
    return [row[0] for row in rows]


def bind_and_print(client: HexinClient, ctx: dict) -> None:
    plan_ids = _plan_ids(ctx)
    if not plan_ids:
        raise ChainError("print", "未找到拣货计划")
    _post(client, "print", "/wms/pickingPlan/bindPicker",
          {"planIds": plan_ids, "bindTargetPicker": PICKER_USER_ID, "bindWaitPickOnly": True})
    rows = fetch_all(
        "hexin_wms",
        "select picking_group, warehouse_id, picker from wms_picking_plan where id=%s",
        (plan_ids[0],),
    )
    picking_group, warehouse_id, picker = rows[0]
    res = _post(client, "print", "/wms/pickingPlan/printAdvance", {
        "planIds": plan_ids,
        "pickingGroup": picking_group,
        "warehouseId": warehouse_id,
        "picker": picker,
        "pickingPrintType": "picking",
        "pickingPrintTime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "pickingPrintMethod": "piece_picking",
    })
    data = res.data or {}
    ctx["picking_order_nos"] = data.get("pickingOrderNos") or ([data["pickingOrderNo"]] if data.get("pickingOrderNo") else [])


def complete_pick(client: HexinClient, ctx: dict) -> None:
    for picking_order_no in ctx["picking_order_nos"]:
        rows = fetch_all(
            "hexin_wms",
            "select outbound_order_no, picking_sku, operation_qty, inventory_id, loc_id "
            "from wms_picking_detail where picking_order_no=%s and del_flag='0'",
            (picking_order_no,),
        )
        details = [
            {"outboundOrderNo": out_no, "pickingSku": sku, "operationQty": int(qty),
             "inventoryId": inventory_id, "locId": loc_id}
            for out_no, sku, qty, inventory_id, loc_id in rows
        ]
        _post(client, "pick", "/wms/pickList/completePick",
              {"orders": [{"pickingOrderNo": picking_order_no, "details": details}]})


def scan_and_check(client: HexinClient, ctx: dict) -> None:
    for pkg in ctx["packages"]:
        _post(client, "check", "/wms/checkTask/scanPackage", {
            "packageNo": pkg["package_no"],
            "warehouseId": WAREHOUSE_ID,
            "logisticsTypeId": pkg.get("logistics_type_id"),
        })
        _post(client, "check", "/wms/checkTask/submitWeight/package", {
            "packageNo": pkg["package_no"],
            "ckWeight": 1,
            "outboundOrderNo": pkg["out_no"],
        })


def generate_delivery(client: HexinClient, ctx: dict) -> None:
    plan_ids = _plan_ids(ctx)
    if not plan_ids:
        raise ChainError("delivery", "未找到拣货计划")
    res = _post(client, "delivery", "/wms/pickingPlan/delivery/generate/confirm",
                {"planIds": plan_ids})
    ctx["delivery_nos"] = res.data or []
    if not ctx["delivery_nos"]:
        raise ChainError("delivery", "未生成提货单号")


def upload(client: HexinClient, ctx: dict) -> None:
    rows = fetch_all(
        "hexin_wms",
        "select id, delivery_no from wms_delivery_order "
        "where delivery_no = any(%s) and del_flag='0'",
        (ctx["delivery_nos"],),
    )
    if not rows:
        raise ChainError("upload", "未找到提货单")
    for delivery_id, _ in rows:
        res = client.post_multipart(
            "/wms/deliveryOrder/uploadAttachment",
            files={"file": ("batch.png", PROBE_PNG, "image/png")},
            params={"deliveryOrderId": delivery_id},
        )
        if not res.ok:
            raise ChainError("upload", res.msg or f"HTTP {res.code}")


def run_chain(client: HexinClient, external_no: str, ctx: dict | None = None, on_stage=None) -> dict:
    ctx = ctx if ctx is not None else {}
    ctx["external_no"] = external_no

    def stage(name: str) -> None:
        ctx["stage"] = name
        if on_stage:
            on_stage(ctx)

    stage("创建订单")
    ctx.update(create_order(client, external_no))
    stage("提交审批")
    approve_order(client, ctx)
    stage("等待包裹")
    ctx["packages"] = wait_packages(ctx)
    stage("选择物流方式")
    select_logistics(client, ctx)
    stage("转仓")
    transfer(client, ctx)
    stage("绑定拣货员并打印")
    bind_and_print(client, ctx)
    stage("完成拣货")
    complete_pick(client, ctx)
    stage("核单称重")
    scan_and_check(client, ctx)
    stage("生成提货单")
    generate_delivery(client, ctx)
    stage("上传附件")
    upload(client, ctx)
    stage("完成")
    return ctx
