"""生成脚本分类附录（回滚/修数据/种子/未登记/缺文件/破坏性）。"""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(r"C:/project/hexincloud")
TOOL = Path(__file__).resolve().parent
rows = json.loads((TOOL / "db_audit_final.json").read_text(encoding="utf-8"))
by_path = {r["path"]: r for r in rows}
ledger_rows = json.loads((TOOL / "ledger.json").read_text(encoding="utf-8"))
led = {r[1].strip().replace("\\", "/"): r for r in ledger_rows if r[1].strip()}

disk = sorted(p.relative_to(REPO).as_posix() for p in REPO.glob("script/sql/releases/20*/**/*.sql"))


def state(path: str) -> str:
    r = by_path.get(path)
    return f"{r['dev']}/{r['test']}/{r['prod']}" if r else "（回滚不探测）"


out = []
out.append("# 脚本分类附录（2026-10-19）\n")

out.append("## 1. 回滚脚本（32 个，均未执行，待命）\n")
out.append("| 回滚脚本 | 正向脚本 | 台账 |")
out.append("|---|---|---|")
for p in disk:
    if not p.endswith("_rollback.sql"):
        continue
    base = p[:-len("_rollback.sql")] + ".sql"
    l = led.get(p)
    out.append(f"| `{p}` | `{base}`{' ✅' if (REPO/base).exists() else ' ❌缺失'} | {l[4] if l else '未登记'} |")

out.append("\n## 2. 修数据脚本（dml/migrate + validate + dml/other，共 38 个）\n")
out.append("| 脚本 | 类型 | dev/test/prod 实测 | 台账 |")
out.append("|---|---|---|---|")
for p in disk:
    if not (re.search(r"/dml/(migrate|other)/", p) or "/validate/" in p):
        continue
    l = led.get(p)
    lstr = f"{l[4]}/{l[5]}/{l[7]}" if l else "未登记"
    kind = "migrate" if "/dml/migrate/" in p else ("validate" if "/validate/" in p else "other")
    out.append(f"| `{p}` | {kind} | {state(p)} | {lstr} |")

out.append("\n## 3. 种子/初始化数据脚本（dml/seed，21 个）\n")
out.append("| 脚本 | dev/test/prod 实测 | 台账 | 说明 |")
out.append("|---|---|---|---|")
notes = {
    "01_md_bank_seed.sql": "参考数据，需 DBA 手工执行",
    "01_pda_client.sql": "MySQL 方言，PG 不执行",
    "01_md_logistics_carrier_code_init.sql": "承运商简码基础数据",
    "01_exception_action_config": "异常任务链配置",
}
for p in disk:
    if "/dml/seed/" not in p:
        continue
    l = led.get(p)
    lstr = f"{l[4]}/{l[5]}/{l[7]}" if l else "未登记"
    note = next((v for k, v in notes.items() if k in p), "功能初始化数据")
    out.append(f"| `{p}` | {state(p)} | {lstr} | {note} |")

out.append("\n## 4. 未登记飞书台账的脚本（不含回滚，52 个）\n")
for r in rows:
    if r["ledger"] == "未登记":
        out.append(f"- `{r['path']}` | dev/test/prod={r['dev']}/{r['test']}/{r['prod']}")

out.append("\n## 5. 飞书台账有、磁盘无（8 条）\n")
for r in ledger_rows:
    p = r[1].strip().replace("\\", "/")
    if p and p.startswith("script/sql/releases/") and not (REPO / p).exists():
        out.append(f"- `{p}` | {r[0]} | dev/test/prod={r[4]}/{r[5]}/{r[7]} | {r[8]}")

out.append("\n## 6. 破坏性脚本且无同名回滚（27 个）\n")
for p in disk:
    if p.endswith("_rollback.sql"):
        continue
    text = (REPO / p).read_text(encoding="utf-8", errors="ignore")
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    text = re.sub(r"--[^\n]*", " ", text)
    hits = []
    for pat, label in [(r"(?i)\bdrop\s+table\b", "DROP TABLE"), (r"(?i)\bdrop\s+column\b", "DROP COLUMN"),
                       (r"(?i)\bdrop\s+constraint\b", "DROP CONSTRAINT"), (r"(?i)\btruncate\s+table\b", "TRUNCATE"),
                       (r"(?i)\bdrop\s+index\b", "DROP INDEX")]:
        if re.search(pat, text):
            hits.append(label)
    if hits and not (REPO / (p[:-4] + "_rollback.sql")).exists():
        out.append(f"- `{p}` | {','.join(hits)} | dev/test/prod={state(p)}")

out.append("\n## 7. 仓库内造数/联调测试数据脚本（不在 releases，禁止发布执行）\n")
TEST_DATA = [
    "hexin-modules/hexin-wms/sql/delivery_order_generate_test_data.sql",
    "hexin-modules/hexin-wms/sql/mp_box260716002_multi_package.sql",
    "hexin-modules/hexin-wms/sql/mp_share_box_multi_package_test_data.sql",
    "hexin-modules/hexin-wms/sql/package_operate_7_6_test_data.sql",
    "hexin-modules/hexin-wms/sql/ur3463_transfer_loss_test_data.sql",
    "hexin-modules/hexin-openapi/sql/fms_freight_sum_to_wms_scenarios_test_data.sql",
    "hexin-modules/hexin-openapi/sql/tts_freight_sum_scenarios_test_data.sql",
]
for p in TEST_DATA:
    out.append(f"- `{p}`")

out.append("\n## 8. 其他未迁入 releases 的模块 SQL（参考，非造数）\n")
others = set()
for p in sorted(REPO.glob("hexin-modules/**/sql/*.sql")):
    rel = p.relative_to(REPO).as_posix()
    if rel in TEST_DATA or "/target/" in rel:
        continue
    others.add(rel)
for p in sorted(REPO.glob("hexin-modules/**/resources/mapper/init/sql/*.sql")):
    others.add(p.relative_to(REPO).as_posix())
for rel in sorted(others):
    out.append(f"- `{rel}`")

(TOOL / "appendix.md").write_text("\n".join(out), encoding="utf-8")
print("written", len(out), "lines")
