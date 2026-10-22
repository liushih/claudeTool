import re
from collections import defaultdict
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
exec(open(Path(__file__).resolve().parent / "classify_prod.py", encoding="utf-8").read().split("gaps = ")[0])

gaps = [r for r in rows if r["prod"] in ("未执行", "部分执行") and r["dev"] == "已执行" and r["test"] == "已执行"]
# 排除回滚
gaps = [r for r in gaps if classify(r) != "rollback"]
ORDER = {"ddl": 0, "dict": 1, "menu": 2, "perm": 3, "config": 4, "seed": 5, "migrate": 6,
         "data-fix": 7, "dml-other": 7, "new-table": 0, "alter-existing": 0, "index-only": 0,
         "ddl-other": 0, "erp-migrate": 6}

by_date = defaultdict(list)
for r in gaps:
    by_date[r["date"]].append(r)

def risk(r):
    t = (REPO / r["path"]).read_text(encoding="utf-8", errors="ignore")
    low = t.lower()
    if "md_customer" in low and "drop table" in low:
        return "🚫ERP "
    if re.search(r"(?im)^\s*(drop\s+table|truncate|delete\s+from)\b", t):
        return "⚠ "
    return ""

print("\n## F. 按日包执行顺序（prod 统一批次）")
print()
print("> ☐ 待执行；⚠ 含 DROP/TRUNCATE/DELETE，执行前先核对目标表与数据量；🚫ERP 为 ERP 存量表脚本，需单独迁移方案。")
print()
for d in sorted(by_date):
    items = sorted(by_date[d], key=lambda r: (ORDER.get(classify(r), 9), r["path"]))
    print(f"### {d}（{len(items)}）")
    for r in items:
        print(f"- ☐ {risk(r)}`{r['path']}`")
    print()
