"""探针：按真实业务链路造 1 张「已上传」提货单。分步执行，每步打印请求/响应。"""

from __future__ import annotations

import json
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

import psycopg

from hexin_client import HexinClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hxpaths import DB_ENV_FILE  # noqa: E402

WAREHOUSE_ID = 565          # 厦门普货仓
STORE_ID = 19266            # B2D-ALI-004-LB
STORE_CODE = "B2D-ALI-004-LB"
PLATFORM_ID = 17
SKU_ID = 204005
SKU = "MT200277-BE1s-XL/XXL"
SKU_NAME = "束身衣"
LOGISTICS_TYPE_ID = 13      # B2D：DHL快递-604083014-20kg以上


def banner(text: str) -> None:
    print(f"\n{'=' * 8} {text} {'=' * 8}")


def show(label: str, result) -> None:
    print(f"[{label}] {result}")


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


def query_one(sql: str, params: tuple = ()):
    with db_connect("hexin_oms") as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def build_basic(external_order_no: str) -> dict:
    return {
        "manualOrderSource": "customer_order",
        "platformId": PLATFORM_ID,
        "storeCode": STORE_CODE,
        "storeId": STORE_ID,
        "externalOrderNo": external_order_no,
        "platformCurrency": "USD",
        "orderSalesman": "admin",
        "orderRemark": "probe data",
    }


def build_customer() -> dict:
    return {
        "receiverName": "Probe Buyer",
        "buyerName": "Probe Buyer",
        "receiverPhone": "13800138000",
        "receiverEmail": "probe@example.com",
        "countryName": "United States",
        "countryCode": "US",
        "provinceName": "California",
        "provinceCode": "CA",
        "cityName": "Los Angeles",
        "postCode": "90001",
        "addressLines": "123 Main St",
    }


def build_payment() -> dict:
    return {
        "settlementMethod": "immediate_pay",
        "totalAmount": 10,
        "freightAmount": 0,
        "goodsTotalTax": 0,
        "lines": [
            {
                "lineNo": 1,
                "payMethod": "bank_transfer",
                "paidAmount": 10,
                "payCurrency": "USD",
                "payRatio": 100,
            }
        ],
    }


def stage_item() -> dict:
    return {
        "sysSkuId": SKU_ID,
        "sysSku": SKU,
        "sysSkuName": SKU_NAME,
        "orderQty": 1,
        "unitPriceExclTax": 10,
        "unitWeight": 0.2,
    }


def main() -> None:
    client = HexinClient()
    external_no = "PROBE-" + datetime.now().strftime("%Y%m%d%H%M%S")
    draft_id = str(uuid.uuid4())

    banner("1. 工作区追加商品")
    res = client.post(
        "/oms/manualOrder/item-stage/items",
        [stage_item()],
        params={"clientDraftId": draft_id},
    )
    show("append", res)
    if not res.ok:
        sys.exit(1)

    banner("2. 取工作区令牌")
    res = client.get("/oms/manualOrder/item-stage/summary", {"clientDraftId": draft_id})
    show("summary", res)
    if not res.ok:
        sys.exit(1)
    stage_token = (res.data or {}).get("stageToken")
    print("stageToken =", stage_token)
    if not stage_token:
        sys.exit("未拿到 stageToken")

    banner("3. 创建手工单")
    body = {
        "basicInfo": build_basic(external_no),
        "customerInfo": build_customer(),
        "paymentInfo": build_payment(),
        "clientDraftId": draft_id,
        "stageToken": stage_token,
    }
    res = client.post("/oms/manualOrder", body)
    show("create", res)
    if not res.ok:
        sys.exit(1)
    task_id = res.data
    print("task_id =", task_id)

    banner("4. 轮询订单落库")
    row = None
    for i in range(15):
        time.sleep(2)
        row = query_one(
            "select id, order_no, order_status from oms_order where external_order_no=%s and del_flag='0'",
            (external_no,),
        )
        if row:
            break
        print(f"  等待中... ({(i + 1) * 2}s)")
    if not row:
        with db_connect("hexin_resource") as conn, conn.cursor() as cur:
            cur.execute("select biz_status, left(payload,600) from sys_user_message where id=%s", (int(task_id),))
            print("任务状态:", cur.fetchone())
        sys.exit("订单未落库")
    print(f"order_id={row[0]} order_no={row[1]} status={row[2]}")


if __name__ == "__main__":
    main()
