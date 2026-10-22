"""脚本 × 台账 × 三环境实际对象 三方比对。只读。"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).with_name("sql_sync_check.py")))
import psycopg  # noqa: E402
import sql_sync_check as chk  # noqa: E402

TOOL = Path(__file__).resolve().parent
LEDGER = TOOL / "ledger.json"
REPO = chk.REPO
RELEASES = chk.RELEASES

ENVS = ["dev", "test", "prod"]
PREFIX_DB = chk.PREFIX_DB
SYS_DB = chk.SYS_DB
MODULE_DB = {
    "oms": "hexin_oms",
    "wms": "hexin_wms",
    "hexin-wms": "hexin_wms",
    "masterdata": "hexin_masterdata",
    "openapi": "hexin_openapi",
    "job": "hexin_job",
    "log": "hexin_log",
    "resource": "hexin_resource",
    "workflow": "hexin_workflow",
    "system": "hexin_masterdata",
    "gen": "hexin_gen",
    "config": "hexin_config",
}


def module_db(path: str) -> str | None:
    parts = path.split("/")
    # script/sql/releases/<date>/<module>/...
    if len(parts) > 4:
        return MODULE_DB.get(parts[4])
    return None


def kind_of(path: str) -> str:
    if Path(path).name.lower().endswith("_rollback.sql"):
        return "rollback"
    for t in ("dml/dict", "dml/menu", "dml/perm", "dml/seed", "dml/migrate", "dml/config", "validate"):
        if f"/{t}/" in path:
            return t
    if "/ddl/" in path:
        return "ddl"
    return "dml/other"


class Catalog:
    def __init__(self, env: str):
        self.env = env
        self.conns: dict[str, psycopg.Connection] = {}
        self.table_dbs: dict[str, list[str]] = defaultdict(list)
        self.index_by_db: dict[str, set[str]] = defaultdict(set)
        self.cols: dict[tuple[str, str], set[str]] = {}
        self.cons: dict[str, set[str]] = defaultdict(set)
        self._cache: dict[tuple, object] = {}
        self.pref: str | None = None
        self._load()

    def conn(self, db: str) -> psycopg.Connection:
        if db not in self.conns:
            self.conns[db] = chk.connect(self.env, db)
        return self.conns[db]

    def _load(self):
        with self.conn("postgres") as c:
            dbs = [r[0] for r in c.execute("select datname from pg_database where not datistemplate")]
        for db in dbs:
            if db in {"postgres", "template0", "template1"}:
                continue
            try:
                c = self.conn(db)
                for (t,) in c.execute("select tablename from pg_tables where schemaname='public'"):
                    self.table_dbs[t].append(db)
                for (i,) in c.execute("select indexname from pg_indexes where schemaname='public'"):
                    self.index_by_db[db].add(i)
            except Exception:
                continue

    def db_for(self, table: str) -> str | None:
        cands = self.table_dbs.get(table, [])
        if not cands:
            return None
        if self.pref in cands:
            return self.pref
        pref = PREFIX_DB.get(next((p for p in PREFIX_DB if table.startswith(p)), ""), None)
        return pref if pref in cands else cands[0]

    def columns(self, db: str, table: str) -> set[str]:
        key = (db, table)
        if key not in self.cols:
            try:
                rows = self.conn(db).execute(
                    """select a.attname from pg_attribute a
                       join pg_class c on a.attrelid=c.oid
                       join pg_namespace n on c.relnamespace=n.oid
                       where n.nspname='public' and c.relname=%s and a.attnum>0 and not a.attisdropped""",
                    (table,),
                )
                self.cols[key] = {r[0] for r in rows}
            except Exception:
                self.cols[key] = set()
        return self.cols[key]

    def dict_info(self, dtype: str) -> tuple[bool, int]:
        key = ("dict", dtype)
        if key not in self._cache:
            try:
                c = self.conn(SYS_DB)
                ex = c.execute("select 1 from sys_dict_type where dict_type=%s", (dtype,)).fetchone()
                n = c.execute("select count(*) from sys_dict_data where dict_type=%s", (dtype,)).fetchone()[0]
                self._cache[key] = (bool(ex), n)
            except Exception:
                self._cache[key] = (False, -1)
        return self._cache[key]

    def menu_perm(self, perm: str) -> bool:
        key = ("perm", perm)
        if key not in self._cache:
            try:
                self._cache[key] = self.conn(SYS_DB).execute(
                    "select 1 from sys_menu where perms=%s", (perm,)
                ).fetchone() is not None
            except Exception:
                self._cache[key] = False
        return self._cache[key]

    def config(self, k: str) -> bool:
        key = ("cfg", k)
        if key not in self._cache:
            try:
                self._cache[key] = self.conn(SYS_DB).execute(
                    "select 1 from sys_config where config_key=%s", (k,)
                ).fetchone() is not None
            except Exception:
                self._cache[key] = False
        return self._cache[key]

    def check(self, p: dict) -> bool | None:
        k = p["kind"]
        if k == "table":
            return bool(self.table_dbs.get(p["table"])) if p["expect"] else None
        if k == "index":
            if p.get("table"):
                db = self.db_for(p["table"])
                if db is None:
                    return False if p["expect"] else None
                found = p["name"] in self.index_by_db.get(db, set())
            else:
                found = any(p["name"] in s for s in self.index_by_db.values())
            return found if p["expect"] else not found
        if k == "dict_type":
            ex, n = self.dict_info(p["name"])
            return ex and n > 0
        if k == "menu_perm":
            return self.menu_perm(p["name"])
        if k == "config":
            return self.config(p["name"])
        if k == "column":
            db = self.db_for(p["table"])
            if db is None:
                return False if p["expect"] else None
            return p["name"] in self.columns(db, p["table"])
        if k == "constraint":
            db = self.db_for(p["table"]) if p.get("table") else None
            if db is None:
                # constraint without table: search all dbs
                found = False
                for d in set(self.index_by_db):
                    pass
                return None
            key = ("cons", db)
            if key not in self._cache:
                try:
                    self._cache[key] = set(
                        r[0] for r in self.conn(db).execute("select conname from pg_constraint")
                    )
                except Exception:
                    self._cache[key] = set()
            return p["name"] in self._cache[key]
        return None


def evaluate(cat: Catalog, probes: list[dict]) -> tuple[str, bool]:
    positives = [p for p in probes if p.get("expect")]
    if not positives:
        return chk.UNKNOWN, False
    res = [cat.check(p) for p in positives]
    known = [r for r in res if r is not None]
    if not known:
        return chk.UNKNOWN, False
    if all(known):
        return chk.DONE, True
    if not any(known):
        return chk.TODO, False
    return chk.PARTIAL, True


def failed_probes(cat: Catalog, probes: list[dict]) -> list[str]:
    out = []
    for p in probes:
        if p.get("expect") and cat.check(p) is False:
            if p["kind"] == "column":
                out.append(f"column:{p['table']}.{p['name']}")
            elif p["kind"] == "table":
                out.append(f"table:{p['table']}")
            else:
                out.append(f"{p['kind']}:{p.get('table') or ''}{'.' if p.get('table') else ''}{p.get('name', '')}")
    return out


def main():
    ledger_rows = json.loads(LEDGER.read_text(encoding="utf-8"))
    led = {}
    for r in ledger_rows:
        p = r[1].strip().replace("\\", "/")
        if p:
            led[p] = {"task": r[0], "dev": r[4], "test": r[5], "prod": r[7], "note": r[8]}

    disk = sorted(p.relative_to(REPO).as_posix() for p in RELEASES.glob("20*/**/*.sql"))
    disk = [p for p in disk if not (Path(p).name.lower().endswith("_rollback.sql") or "/rollback/" in p.lower())]
    print(f"待核查 {len(disk)} 个脚本（不含回滚）", file=sys.stderr)

    cats = {e: Catalog(e) for e in ENVS}
    out = []
    counts = {e: Counter() for e in ENVS}
    mismatches = []

    for i, path in enumerate(disk, 1):
        text = (REPO / path).read_text(encoding="utf-8", errors="ignore")
        probes = chk.parse_probes(text)
        d = chk.dialect(path)
        for e in ENVS:
            cats[e].pref = module_db(path)
        if d != "PG":
            states = {e: "不应执行" for e in ENVS}
        else:
            states = {e: evaluate(cats[e], probes)[0] for e in ENVS}
        l = led.get(path)
        lstr = f"{l['dev']}/{l['test']}/{l['prod']}" if l else "未登记"
        diag = {e: failed_probes(cats[e], probes) for e in ENVS if states[e] in (chk.TODO, chk.PARTIAL)}
        row = {"path": path, "kind": kind_of(path), "ledger": lstr,
               "dev": states["dev"], "test": states["test"], "prod": states["prod"],
               "diag": diag}
        out.append(row)
        for e in ENVS:
            counts[e][states[e]] += 1
        if l:
            for e, flag in (("dev", l["dev"]), ("test", l["test"]), ("prod", l["prod"])):
                if flag == "✅" and states[e] in (chk.TODO, chk.PARTIAL):
                    mismatches.append((path, e, "台账✅但库中未执行/部分", states[e]))
                if flag == "⬜" and states[e] == chk.DONE:
                    mismatches.append((path, e, "台账⬜但库中已存在", states[e]))
        if i % 50 == 0:
            print(f"  {i}/{len(disk)}", file=sys.stderr)

    json.dump(out, open(TOOL / "db_audit.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n== 三环境实际状态统计 ==")
    for e in ENVS:
        print(e, dict(counts[e]))
    print(f"\n== 台账与实际不一致 {len(mismatches)} 条 ==")
    for m in mismatches:
        print(" | ".join(map(str, m)))

    for e in ENVS:
        print(f"\n== {e} 未执行/部分执行（PG 且非不应执行） ==")
        for r in out:
            if r[e] in (chk.TODO, chk.PARTIAL):
                d = ";".join(r.get("diag", {}).get(e, [])[:6])
                print(f"  [{r[e]}] {r['path']} | 台账 {r['ledger']} | {d}")


if __name__ == "__main__":
    main()
