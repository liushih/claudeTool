"""数据库连接与 SQL 执行。"""

from __future__ import annotations

import psycopg


class DbError(Exception):
    pass


def connect(env: dict[str, str], prefix: str, database: str):
    keys = {
        "host": f"{prefix}_HOST",
        "port": f"{prefix}_PORT",
        "user": f"{prefix}_USER",
        "password": f"{prefix}_PASSWORD",
    }
    missing = [name for name in keys.values() if not env.get(name)]
    if missing:
        raise DbError(f"{', '.join(missing)} 未配置")

    return psycopg.connect(
        host=env[keys["host"]],
        port=int(env[keys["port"]]),
        user=env[keys["user"]],
        password=env[keys["password"]],
        dbname=database,
        connect_timeout=10,
    )


def execute(conn, sql: str, params=None) -> tuple[list[tuple], int]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall() if cur.description else []
        return rows, cur.rowcount
