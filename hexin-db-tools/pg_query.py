"""只读 PostgreSQL 查询工具。用法见 --help。"""

import argparse
import os
import re
import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

ENV_FILE = Path(__file__).with_name(".env")
WRITE_PATTERN = re.compile(
    r"^\s*(insert|update|delete|drop|alter|create|truncate|grant|revoke|copy|merge|call|do|vacuum|analyze|refresh|reindex|cluster|set)\b",
    re.IGNORECASE,
)


def load_env(name: str) -> dict:
    values = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        values[key.strip()] = val.strip()
    prefix = name.upper()
    return {
        "host": values[f"{prefix}_HOST"],
        "port": values[f"{prefix}_PORT"],
        "user": values[f"{prefix}_USER"],
        "password": values[f"{prefix}_PASSWORD"],
    }


def connect(env_name: str, dbname: str | None):
    conf = load_env(env_name)
    return psycopg.connect(
        host=conf["host"],
        port=conf["port"],
        user=conf["user"],
        password=conf["password"],
        dbname=dbname or conf["user"],
        options="-c default_transaction_read_only=on",
        connect_timeout=10,
    )


def ensure_readonly(sql: str):
    if WRITE_PATTERN.match(sql):
        sys.exit("拒绝执行：本工具只允许只读语句（SELECT / SHOW / WITH / EXPLAIN）。")


def print_rows(rows):
    if not rows:
        print("(0 rows)")
        return
    columns = list(rows[0].keys())
    widths = {c: len(c) for c in columns}
    for row in rows:
        for c in columns:
            widths[c] = max(widths[c], len(str(row[c])))
    print(" | ".join(c.ljust(widths[c]) for c in columns))
    print("-+-".join("-" * widths[c] for c in columns))
    for row in rows:
        print(" | ".join(str(row[c]).ljust(widths[c]) for c in columns))
    print(f"({len(rows)} rows)")


def main():
    parser = argparse.ArgumentParser(description="只读查询 hexincloud PostgreSQL")
    parser.add_argument("--env", choices=["prod", "test", "dev"], required=True)
    parser.add_argument("--db", help="数据库名，默认与用户名相同")
    parser.add_argument("--sql", help="只读 SQL")
    parser.add_argument("--list-dbs", action="store_true", help="列出可连接的数据库")
    parser.add_argument("--list-schemas", action="store_true", help="列出当前库的 schema")
    parser.add_argument("--list-tables", metavar="SCHEMA", help="列出指定 schema 的表")
    args = parser.parse_args()

    with connect(args.env, args.db) as conn:
        conn.read_only = True
        with conn.cursor(row_factory=dict_row) as cur:
            if args.list_dbs:
                cur.execute("select datname from pg_database where not datistemplate order by datname")
                print_rows(cur.fetchall())
            elif args.list_schemas:
                cur.execute("select nspname from pg_namespace where nspname not like 'pg\\_%' order by nspname")
                print_rows(cur.fetchall())
            elif args.list_tables:
                cur.execute(
                    "select tablename from pg_tables where schemaname = %s order by tablename",
                    (args.list_tables,),
                )
                print_rows(cur.fetchall())
            elif args.sql:
                ensure_readonly(args.sql)
                cur.execute(args.sql)
                if cur.description:
                    print_rows(cur.fetchall())
                else:
                    print("OK")
            else:
                parser.error("需要 --sql 或 --list-* 参数")


if __name__ == "__main__":
    main()
