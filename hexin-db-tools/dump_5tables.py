"""导出五张表在指定环境的结构明细（UTF-8）。"""

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

SQL = {
    "columns": """
        select a.attnum as pos, a.attname as name,
               format_type(a.atttypid, a.atttypmod) as type,
               a.attnotnull as notnull,
               coalesce(pg_get_expr(d.adbin, d.adrelid), '') as default_expr,
               coalesce(col_description(a.attrelid, a.attnum), '') as comment
        from pg_attribute a
        left join pg_attrdef d on d.adrelid = a.attrelid and d.adnum = a.attnum
        where a.attrelid = to_regclass(%s) and a.attnum > 0 and not a.attisdropped
        order by a.attnum
    """,
    "indexes": """
        select indexname, indexdef from pg_indexes
        where schemaname='public' and tablename=%s order by indexname
    """,
    "constraints": """
        select conname, contype, pg_get_constraintdef(oid) as def
        from pg_constraint where conrelid = to_regclass(%s) order by conname
    """,
    "sequences": """
        select s.schemaname, s.sequencename, s.increment_by, s.start_value,
               s.min_value, s.max_value, s.cycle,
               a.attname as owned_by_column
        from pg_sequences s
        left join pg_depend d on d.objid = to_regclass(quote_ident(s.schemaname)||'.'||quote_ident(s.sequencename))
             and d.deptype in ('a','i')
        left join pg_attribute a on a.attrelid = d.refobjid and a.attnum = d.refobjsubid
        where s.schemaname='public' and (
            a.attrelid = to_regclass(%s)
            or s.sequencename like %s
        )
    """,
    "table_comment": """
        select obj_description(to_regclass(%s), 'pg_class') as comment
    """,
}


def main():
    env = sys.argv[1] if len(sys.argv) > 1 else "test"
    out = []
    for db, table in TABLES:
        fq = f"public.{table}"
        with connect(env, db) as conn:
            conn.read_only = True
            with conn.cursor(row_factory=dict_row) as cur:
                out.append(f"\n########## {db}.{table} ##########")
                cur.execute(SQL["table_comment"], (fq,))
                out.append(f"-- table comment: {cur.fetchone()['comment']}")
                cur.execute(SQL["columns"], (fq,))
                out.append("-- columns")
                for r in cur.fetchall():
                    out.append(
                        f"  {r['pos']:>3} {r['name']:<32} {r['type']:<28} "
                        f"notnull={r['notnull']} default={r['default_expr']!r} comment={r['comment']!r}"
                    )
                cur.execute(SQL["constraints"], (fq,))
                out.append("-- constraints")
                for r in cur.fetchall():
                    out.append(f"  {r['conname']} [{r['contype']}] {r['def']}")
                cur.execute(SQL["indexes"], (table,))
                out.append("-- indexes")
                for r in cur.fetchall():
                    out.append(f"  {r['indexname']}: {r['indexdef']}")
                cur.execute(SQL["sequences"], (fq, f"{table}_%_seq"))
                out.append("-- sequences")
                for r in cur.fetchall():
                    out.append(f"  {r}")
    text = "\n".join(out)
    path = f"dump_5tables_{env}.txt"
    open(path, "w", encoding="utf-8").write(text)
    print(text)


if __name__ == "__main__":
    main()
