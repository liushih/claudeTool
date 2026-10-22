"""只读查询助手：dict 输出，避免列名猜测。用法: python q.py <db> "<sql>" [limit]"""

import sys

import psycopg
from psycopg.rows import dict_row

from probe_step import db_connect


def main() -> None:
    dbname, sql = sys.argv[1], sys.argv[2]
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    with db_connect(dbname) as conn:
        conn.read_only = True
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql)
            rows = cur.fetchall()
    if limit:
        rows = rows[:limit]
    for row in rows:
        for key, value in row.items():
            text = str(value)
            if len(text) > 200:
                text = text[:200] + "..."
            print(f"  {key}: {text}")
        print("-" * 40)
    print(f"({len(rows)} rows)")


if __name__ == "__main__":
    main()
