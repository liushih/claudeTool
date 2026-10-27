"""MongoDB 连接与查询执行。"""

from __future__ import annotations

import pymongo

WRITE_OPS = {"insert", "update", "delete"}


class MongoError(Exception):
    pass


class MongoClient:
    def __init__(self, uri: str, database: str, client=None):
        self.database = database
        self.client = client or pymongo.MongoClient(uri)

    def run(self, collection: str, op: str, payload, limit: int | None = None):
        coll = self.client[self.database][collection]

        if op == "find":
            return list(coll.find(payload or {}, limit=limit or 0))
        if op == "aggregate":
            return list(coll.aggregate(payload or []))
        if op == "count":
            return coll.count_documents(payload or {})
        if op == "insert":
            if isinstance(payload, list):
                coll.insert_many(payload)
            else:
                coll.insert_one(payload or {})
            return "ok"
        if op == "update":
            filter_ = (payload or {}).get("filter", {})
            update = (payload or {}).get("update", {})
            if (payload or {}).get("many"):
                coll.update_many(filter_, update)
            else:
                coll.update_one(filter_, update)
            return "ok"
        if op == "delete":
            filter_ = (payload or {}).get("filter", {})
            if (payload or {}).get("many"):
                coll.delete_many(filter_)
            else:
                coll.delete_one(filter_)
            return "ok"

        raise MongoError(f"未知操作 {op}")


def connect(env: dict, prefix: str, database: str) -> MongoClient:
    uri = env.get(f"{prefix}_URI")
    if not uri:
        raise MongoError(f"{prefix}_URI 未配置")
    return MongoClient(uri, database)
