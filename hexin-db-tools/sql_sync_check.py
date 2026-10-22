"""核查磁盘脚本是否已在 dev/test/prod 执行（以脚本目标对象是否存在为依据）。"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

import psycopg

TOOL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOL_DIR.parent))
from hxpaths import REPO, SKILL_SCRIPTS  # noqa: E402

ENV_FILE = TOOL_DIR / ".env"
FEISHU_SCRIPTS = SKILL_SCRIPTS
RELEASES = REPO / "script/sql/releases"

DONE, PARTIAL, TODO, UNKNOWN = "已执行", "部分执行", "未执行", "无法校验"

ENVS = {
    "dev": ("DEV", "hexincloud_crw"),
    "test": ("TEST", "dev_test_crw"),
    "prod": ("PROD", "hexincloud_crw"),
}
SYS_DB = "hexin_masterdata"
PREFIX_DB = {"sys_": SYS_DB, "oms_": "hexin_oms", "wms_": "hexin_wms", "md_": SYS_DB}


def load_env() -> dict:
    values = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, val = line.split("=", 1)
            values[key.strip()] = val.strip()
    return values


ENV = load_env()


def connect(env: str, dbname: str):
    prefix = ENVS[env][0]
    return psycopg.connect(
        host=ENV[f"{prefix}_HOST"],
        port=ENV[f"{prefix}_PORT"],
        user=ENV[f"{prefix}_USER"],
        password=ENV[f"{prefix}_PASSWORD"],
        dbname=dbname,
        options="-c default_transaction_read_only=on",
        connect_timeout=10,
    )


def ledger_paths() -> set[str]:
    sys.path.insert(0, str(FEISHU_SCRIPTS))
    import feishu_sheet as fs  # noqa: E402

    class Args:
        env_file = None
        sheet_id = None

    _, access, ss_token, sheet_id = fs.connect(Args())
    values = fs.read_range(ss_token, access, f"{sheet_id}!A1:I5000")
    out = set()
    for row in values[1:]:
        cells = list(row) + [""] * (9 - len(row))
        if cells[1] not in (None, ""):
            out.add(str(cells[1]).strip().replace("\\", "/"))
    return out


def disk_scripts() -> list[str]:
    out = []
    for path in RELEASES.glob("20*/**/*.sql"):
        rel = path.relative_to(REPO).as_posix()
        out.append(rel)
    return sorted(out)


def strip_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    sql = re.sub(r"--[^\n]*", " ", sql)
    return sql


def split_statements(sql: str) -> list[str]:
    parts, buf, depth = [], [], 0
    quote = None
    for ch in sql:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in ("'", '"'):
            quote = ch
            buf.append(ch)
        elif ch == "(":
            depth += 1
            buf.append(ch)
        elif ch == ")":
            depth -= 1
            buf.append(ch)
        elif ch == ";" and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    if "".join(buf).strip():
        parts.append("".join(buf).strip())
    return [p for p in parts if p]


def split_top_commas(text: str) -> list[str]:
    parts, buf, depth = [], [], 0
    quote = None
    for ch in text:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in ("'", '"'):
            quote = ch
            buf.append(ch)
        elif ch == "(":
            depth += 1
            buf.append(ch)
        elif ch == ")":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    if "".join(buf).strip():
        parts.append("".join(buf).strip())
    return parts


def norm_ident(raw: str) -> str:
    raw = raw.strip().strip('"')
    if "." in raw:
        raw = raw.split(".")[-1].strip('"')
    return raw


IDENT = r'(?:"?[A-Za-z_][\w$]*"?\.)?"?[A-Za-z_][\w$]*"?'


def parse_probes(sql: str) -> list[dict]:
    probes = []
    text = strip_comments(sql)

    for stmt in split_statements(text):
        head = stmt.lstrip().lower()

        m = re.match(rf"(?is)^create\s+table\s+(?:if\s+not\s+exists\s+)?({IDENT})", stmt)
        if m:
            probes.append({"kind": "table", "table": norm_ident(m.group(1)), "expect": True})
            continue

        m = re.match(rf"(?is)^drop\s+table\s+(?:if\s+exists\s+)?({IDENT})", stmt)
        if m:
            probes.append({"kind": "table", "table": norm_ident(m.group(1)), "expect": False})
            continue

        m = re.match(rf"(?is)^alter\s+table\s+(?:if\s+exists\s+)?({IDENT})\s+(.*)$", stmt)
        if m:
            table = norm_ident(m.group(1))
            body = m.group(2).strip()
            if re.match(r"(?is)^rename\s+to\s+", body):
                continue
            for clause in split_top_commas(body):
                cm = re.match(r"(?is)^add\s+(?:column\s+)?(?:if\s+not\s+exists\s+)?(\"?[A-Za-z_][\w$]*\"?)", clause)
                if cm and not re.match(r"(?is)^add\s+constraint\b", clause):
                    probes.append({"kind": "column", "table": table, "name": norm_ident(cm.group(1)), "expect": True})
                    continue
                cm = re.match(r"(?is)^drop\s+column\s+(?:if\s+exists\s+)?(\"?[A-Za-z_][\w$]*\"?)", clause)
                if cm:
                    probes.append({"kind": "column", "table": table, "name": norm_ident(cm.group(1)), "expect": False})
                    continue
                cm = re.match(r"(?is)^rename\s+column\s+(\S+)\s+to\s+(\S+)", clause)
                if cm:
                    probes.append({"kind": "column", "table": table, "name": norm_ident(cm.group(2)), "expect": True})
                    continue
                cm = re.match(r"(?is)^alter\s+column\s+(\"?[A-Za-z_][\w$]*\"?)", clause)
                if cm:
                    probes.append(
                        {"kind": "column", "table": table, "name": norm_ident(cm.group(1)), "expect": True, "weak": True}
                    )
                    continue
                cm = re.match(r"(?is)^add\s+constraint\s+(\"?[A-Za-z_][\w$]*\"?)", clause)
                if cm:
                    probes.append({"kind": "constraint", "table": table, "name": norm_ident(cm.group(1)), "expect": True})
                    continue
                cm = re.match(r"(?is)^drop\s+constraint\s+(?:if\s+exists\s+)?(\"?[A-Za-z_][\w$]*\"?)", clause)
                if cm:
                    probes.append({"kind": "constraint", "table": table, "name": norm_ident(cm.group(1)), "expect": False})
                    continue
            continue

        m = re.match(rf"(?is)^create\s+(?:unique\s+)?index\s+(?:concurrently\s+)?(?:if\s+not\s+exists\s+)?({IDENT})\s+on\s+({IDENT})", stmt)
        if m:
            probes.append({"kind": "index", "table": norm_ident(m.group(2)), "name": norm_ident(m.group(1)), "expect": True})
            continue

        m = re.match(rf"(?is)^drop\s+index\s+(?:concurrently\s+)?(?:if\s+exists\s+)?({IDENT})", stmt)
        if m:
            probes.append({"kind": "index", "table": None, "name": norm_ident(m.group(1)), "expect": False})
            continue

        if re.match(r"(?is)^insert\s+into\s+(?:public\.)?sys_dict_type\b", stmt):
            for dt in re.findall(r"dict_type\s*=\s*'([^']+)'", stmt, flags=re.I):
                probes.append({"kind": "dict_type", "table": "sys_dict_type", "name": dt, "expect": True})
            continue

        if re.match(r"(?is)^insert\s+into\s+(?:public\.)?sys_dict_data\b", stmt):
            for dt in re.findall(r"dict_type\s*=\s*'([^']+)'", stmt, flags=re.I):
                probes.append({"kind": "dict_type", "table": "sys_dict_type", "name": dt, "expect": True})
            continue

        if re.match(r"(?is)^insert\s+into\s+(?:public\.)?sys_menu\b", stmt):
            candidates = re.findall(r"'([A-Za-z][\w]*(?::[A-Za-z][\w]*)+)'", stmt)
            parent = {p for alias, p in re.findall(r"(\w+)\.perms\s*=\s*'([^']+)'", stmt)}
            picked = []
            for cand in dict.fromkeys(candidates):
                if cand in parent and candidates.count(cand) == 1:
                    continue
                picked.append(cand)
            for p in picked:
                probes.append({"kind": "menu_perm", "table": "sys_menu", "name": p, "expect": True})
            continue

        if re.match(r"(?is)^insert\s+into\s+(?:public\.)?sys_config\b", stmt):
            for key in re.findall(r"config_key\s*=\s*'([^']+)'", stmt, flags=re.I):
                probes.append({"kind": "config", "table": "sys_config", "name": key, "expect": True})
            continue

    return probes


class EnvCatalog:
    def __init__(self, env: str):
        self.env = env
        self.table_dbs: dict[str, list[str]] = defaultdict(list)
        self.index_dbs: dict[str, list[str]] = defaultdict(list)
        self.index_by_db: dict[str, set[str]] = defaultdict(set)
        self._dict_counts: dict[str, int] = {}
        self._load()

    def _load(self):
        with connect(self.env, "postgres") as conn:
            dbs = [r[0] for r in conn.execute("select datname from pg_database where not datistemplate order by 1")]
        for db in dbs:
            if db in {"postgres", "template0", "template1"}:
                continue
            try:
                with connect(self.env, db) as conn:
                    for (table,) in conn.execute("select tablename from pg_tables where schemaname='public'"):
                        self.table_dbs[table].append(db)
                    for (idx,) in conn.execute("select indexname from pg_indexes where schemaname='public'"):
                        self.index_dbs[idx].append(db)
                        self.index_by_db[db].add(idx)
            except Exception:
                continue

    def dict_count(self, dict_type: str) -> int:
        if dict_type not in self._dict_counts:
            try:
                with connect(self.env, SYS_DB) as conn:
                    exists = conn.execute(
                        "select 1 from public.sys_dict_type where dict_type=%s", (dict_type,)
                    ).fetchone()
                    if not exists:
                        self._dict_counts[dict_type] = 0
                    else:
                        self._dict_counts[dict_type] = conn.execute(
                            "select count(*) from public.sys_dict_data where dict_type=%s", (dict_type,)
                        ).fetchone()[0]
            except Exception:
                self._dict_counts[dict_type] = -1
        return self._dict_counts[dict_type]

    def check(self, probe: dict) -> bool | None:
        kind = probe["kind"]
        if kind == "table":
            return bool(self.table_dbs.get(probe["table"])) if probe["expect"] else None
        if kind == "index":
            if probe.get("table"):
                candidates = self.table_dbs.get(probe["table"], [])
                if not candidates:
                    return False if probe["expect"] else None
                prefix_db = PREFIX_DB.get(next((p for p in PREFIX_DB if probe["table"].startswith(p)), ""), None)
                idx_db = prefix_db if prefix_db in candidates else candidates[0]
                found = probe["name"] in self.index_by_db.get(idx_db, set())
            else:
                found = probe["name"] in self.index_dbs
            return found if probe["expect"] else not found

        db = None
        if kind in ("dict_type", "menu_perm", "config"):
            db = SYS_DB
        elif probe.get("table"):
            table = probe["table"]
            candidates = self.table_dbs.get(table, [])
            if not candidates:
                return False if probe["expect"] else None
            prefix_db = PREFIX_DB.get(next((p for p in PREFIX_DB if table.startswith(p)), ""), None)
            db = prefix_db if prefix_db in candidates else candidates[0]

        if db is None:
            return None

        try:
            with connect(self.env, db) as conn:
                if kind == "column":
                    found = conn.execute(
                        """select 1 from pg_attribute a
                           join pg_class c on a.attrelid = c.oid
                           join pg_namespace n on c.relnamespace = n.oid
                           where n.nspname='public' and c.relname=%s and a.attname=%s
                             and a.attnum>0 and not a.attisdropped""",
                        (probe["table"], probe["name"]),
                    ).fetchone() is not None
                elif kind == "constraint":
                    found = conn.execute("select 1 from pg_constraint where conname=%s", (probe["name"],)).fetchone() is not None
                elif kind == "dict_type":
                    found = conn.execute("select 1 from public.sys_dict_type where dict_type=%s", (probe["name"],)).fetchone() is not None
                elif kind == "menu_perm":
                    found = conn.execute("select 1 from public.sys_menu where perms=%s", (probe["name"],)).fetchone() is not None
                elif kind == "config":
                    found = conn.execute("select 1 from public.sys_config where config_key=%s", (probe["name"],)).fetchone() is not None
                else:
                    return None
        except Exception:
            return None
        return found if probe["expect"] else not found


def evaluate(catalogs: dict[str, EnvCatalog], probes: list[dict]) -> dict:
    positives = [p for p in probes if p.get("expect")]
    if not positives:
        return {env: UNKNOWN for env in catalogs}
    details = {}
    for env, cat in catalogs.items():
        results = [cat.check(p) for p in positives]
        known = [r for r in results if r is not None]
        if not known:
            details[env] = UNKNOWN
        elif all(known):
            details[env] = DONE
        elif not any(known):
            details[env] = TODO
        else:
            details[env] = PARTIAL
    return details


def evaluate_dict(catalogs: dict[str, EnvCatalog], probes: list[dict]) -> dict:
    types = list(dict.fromkeys(p["name"] for p in probes if p["kind"] == "dict_type"))
    if not types:
        return {env: UNKNOWN for env in catalogs}
    counts = {env: {t: cat.dict_count(t) for t in types} for env, cat in catalogs.items()}
    base = counts.get("dev", {})
    details = {}
    for env, env_counts in counts.items():
        marks = []
        for t in types:
            got, want = env_counts[t], base.get(t, -1)
            if got <= 0:
                marks.append(0)
            elif want > 0 and got == want:
                marks.append(2)
            else:
                marks.append(1)
        if all(m == 2 for m in marks):
            details[env] = DONE
        elif all(m == 0 for m in marks):
            details[env] = TODO
        else:
            details[env] = PARTIAL
    return details


MYSQL_ONLY = re.compile(r"(?i)\b(sysdate|ifnull|date_format|date_add|set\s+@|group_concat)\s*\(|\bset\s+@\w+\s*:=")


def dialect(path: str) -> str:
    text = (REPO / path).read_text(encoding="utf-8", errors="ignore")
    return "MySQL(勿在PG执行)" if MYSQL_ONLY.search(text) else "PG"


def kind_of(path: str) -> str:
    if "rollback" in path:
        return "rollback"
    for t in ("dml/dict", "dml/menu", "dml/perm", "dml/seed", "dml/migrate", "dml/config", "validate"):
        if f"/{t}/" in path:
            return t
    if "/ddl/" in path:
        return "ddl"
    return "dml/other"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="全部磁盘脚本，默认只查未登记")
    parser.add_argument("--env", choices=list(ENVS), action="append", help="只查指定环境")
    args = parser.parse_args()

    registered = ledger_paths()
    scripts = disk_scripts()
    if not args.all:
        scripts = [p for p in scripts if p not in registered and "rollback" not in p]

    envs = args.env or list(ENVS)
    print(f"待核查脚本 {len(scripts)} 个；环境 {', '.join(envs)}", file=sys.stderr)
    catalogs = {e: EnvCatalog(e) for e in envs}

    header = f"{'脚本':78} {'类型':10} {'方言':18} " + " ".join(f"{e:6}" for e in envs)
    print(header)
    print("-" * len(header))
    summary = {e: defaultdict(int) for e in envs}
    for path in scripts:
        probes = parse_probes((REPO / path).read_text(encoding="utf-8", errors="ignore"))
        d = dialect(path)
        if d != "PG":
            details = {e: "不应执行" for e in envs}
        elif kind_of(path) == "dml/dict":
            details = evaluate_dict(catalogs, probes)
        else:
            details = evaluate(catalogs, probes)
        for e in envs:
            summary[e][details.get(e, UNKNOWN)] += 1
        print(f"{path:78} {kind_of(path):10} {d:18} " + " ".join(f"{details.get(e,'?'):6}" for e in envs))
    print()
    for e in envs:
        print(e, dict(summary[e]))


if __name__ == "__main__":
    main()
