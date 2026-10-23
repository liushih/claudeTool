"""按 adapter 的 verify 段执行 SQL 校验。"""

from __future__ import annotations


def run_verify(conn, spec: dict | None, params: dict | None = None) -> tuple[bool, object]:
    if not spec:
        return True, None

    with conn.cursor() as cur:
        cur.execute(spec["sql"], params or {})
        row = cur.fetchone()

    got = row[0] if row else None
    return got == spec.get("expect"), got
