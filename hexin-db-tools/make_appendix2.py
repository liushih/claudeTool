"""生成 prod 缺口分类明细 markdown。"""
from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
exec(open(Path(__file__).resolve().parent / "classify_prod.py", encoding="utf-8").read().split("gaps = ")[0])

gaps = [r for r in rows if r["prod"] in ("未执行", "部分执行") and r["dev"] == "已执行" and r["test"] == "已执行"]
bycat = defaultdict(list)
for r in gaps:
    bycat[classify(r)].append(r)

TITLES = [
    ("alter-existing", "A1. 已有表加列/改列（prod 必须执行，逐条评估）"),
    ("index-only", "A2. 已有表索引（prod 必须执行）"),
    ("new-table", "B1. 新表（统一批次按日包执行）"),
    ("ddl-other", "B2. 新功能附属 ALTER（目标表由同批次新表脚本创建）"),
    ("dict", "C1. 数据字典（sys_dict_*）"),
    ("menu", "C2. 菜单/按钮权限（sys_menu / sys_role_menu）"),
    ("perm", "C3. 其他权限"),
    ("config", "C4. 系统参数（sys_config）"),
    ("dml-other", "D1. 其他数据脚本"),
    ("rollback", "D2. 回滚脚本（不执行）"),
]

ERP = re.compile(r"(?i)\b(ods_|report_|global_stock_erp_|md_)")

out = ["# prod 缺口脚本分类明细（2026-10-20）", "",
       f"来源：`script/sql/releases` 全量 598 个脚本 × dev/test/prod 实测；dev/test 已执行而 prod 未执行的共 **{len(gaps)}** 个。", ""]
for key, title in TITLES:
    items = bycat.get(key, [])
    if not items:
        continue
    out.append(f"## {title}（{len(items)}）")
    out.append("")
    out.append("| 日包 | 脚本 | prod |")
    out.append("|---|---|---|")
    for r in sorted(items, key=lambda x: x["path"]):
        out.append(f"| {r['date']} | `{r['path']}` | {r['prod']} |")
    out.append("")

Path(Path(__file__).resolve().parent / "prod_gap_appendix.md").write_text("\n".join(out), encoding="utf-8")
print("written", len(out), "lines;", {k: len(v) for k, v in bycat.items()})
