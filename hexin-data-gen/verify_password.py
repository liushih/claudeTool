"""只读校验：用 dev 库里的 bcrypt 哈希验证候选密码（不写库、不改库）。"""

import os
import sys
from pathlib import Path

import bcrypt
import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hxpaths import DB_ENV_FILE as ENV_FILE  # noqa: E402


def load_env() -> dict:
    values = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        values[key.strip()] = val.strip()
    return values


def main(candidates: list[str]) -> None:
    env = load_env()
    with psycopg.connect(
        host=env["DEV_HOST"],
        port=env["DEV_PORT"],
        user=env["DEV_USER"],
        password=env["DEV_PASSWORD"],
        dbname="hexin_masterdata",
        options="-c default_transaction_read_only=on",
        connect_timeout=10,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute("select password from sys_user where user_name='admin' and del_flag='0'")
            row = cur.fetchone()
    if not row:
        print("admin 用户不存在")
        return
    hashed = row[0].encode()
    for candidate in candidates:
        matched = bcrypt.checkpw(candidate.encode(), hashed)
        print(f"candidate={candidate!r} -> {'匹配' if matched else '不匹配'}")


if __name__ == "__main__":
    main(sys.argv[1:] or ["Hexin.cloud"])
