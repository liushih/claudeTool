"""比对指定表在 dev/test/prod 的结构，并导出建表语句。"""

import sys

from psycopg.rows import dict_row

from pg_query import connect

TABLES = [
    ("hexin_wms", "wms_picking_cart"),
    ("hexin_wms", "wms_picking_cart_record"),
    ("hexin_masterdata", "md_logistics_group"),
    ("hexin_masterdata", "md_product_size"),
    ("hexin_log", "sys_exception_action_config"),
]

COLUMNS_SQL = """
select ordinal_position as pos,
       column_name,
       data_type,
       coalesce(character_maximum_length::text, '') as len,
       coalesce(numeric_precision::text, '') || case when numeric_scale is not null then ',' || numeric_scale else '' end as prec,
       is_nullable,
       coalesce(column_default, '') as col_default
from information_schema.columns
where table_schema = 'public' and table_name = %s
order by ordinal_position
"""

INDEX_SQL = """
select indexname, indexdef
from pg_indexes
where schemaname = 'public' and tablename = %s
order by indexname
"""

CONSTRAINT_SQL = """
select conname, contype, pg_get_constraintdef(oid) as def
from pg_constraint
where conrelid = to_regclass(%s)
order by conname
"""

TABLE_SQL = """
select c.relname,
       obj_description(c.oid, 'pg_class') as comment,
       pg_get_userbyid(c.relowner) as owner,
       c.relpersistence,
       coalesce(ts.spcname, 'default') as tablespace
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
left join pg_tablespace ts on ts.oid = c.reltablespace
where n.nspname = 'public' and c.relkind = 'r' and c.relname = %s
"""

COLUMN_COMMENTS_SQL = """
select a.attname as column_name, col_description(a.attrelid, a.attnum) as comment
from pg_attribute a
where a.attrelid = to_regclass(%s) and a.attnum > 0 and not a.attisdropped
order by a.attnum
"""


def fetch(conn, sql, params):
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def snapshot(env, db, table):
    with connect(env, db) as conn:
        conn.read_only = True
        fq = f"public.{table}"
        return {
            "table": fetch(conn, TABLE_SQL, (table,)),
            "columns": fetch(conn, COLUMNS_SQL, (table,)),
            "indexes": fetch(conn, INDEX_SQL, (table,)),
            "constraints": fetch(conn, CONSTRAINT_SQL, (fq,)),
            "comments": fetch(conn, COLUMN_COMMENTS_SQL, (fq,)),
        }


def norm(rows):
    out = []
    for r in rows:
        out.append(tuple("" if v is None else str(v) for v in r.values()))
    return out


def diff(label, a, b, keys_a="dev", keys_b="test"):
    sa, sb = norm(a), norm(b)
    if sa == sb:
        print(f"  [{label}] 一致 ({len(sa)} 项)")
        return True
    print(f"  [{label}] 不一致")
    set_a, set_b = set(sa), set(sb)
    for row in sa:
        if row not in set_b:
            print(f"    only {keys_a}: {row}")
    for row in sb:
        if row not in set_a:
            print(f"    only {keys_b}: {row}")
    if sa != sb and set_a == set_b:
        print(f"    顺序不同: {keys_a}={[r[0] for r in sa]} {keys_b}={[r[0] for r in sb]}")
    return False


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "diff"
    all_ok = True
    for db, table in TABLES:
        print(f"\n=== {db}.{table} ===")
        dev = snapshot("dev", db, table)
        test = snapshot("test", db, table)
        ok = True
        for part in ("table", "columns", "indexes", "constraints", "comments"):
            ok = diff(part, dev[part], test[part]) and ok
        all_ok = all_ok and ok
        if mode == "full":
            for part in ("columns", "indexes", "constraints", "comments"):
                print(f"  -- test {part} --")
                for r in test[part]:
                    print("   ", r)
    print("\n总结:", "dev 与 test 结构完全一致" if all_ok else "存在差异，见上")


if __name__ == "__main__":
    main()
