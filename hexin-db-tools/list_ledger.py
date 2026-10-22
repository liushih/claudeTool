"""只读导出飞书 SQL 台账。"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hxpaths import SKILL_SCRIPTS  # noqa: E402

sys.path.insert(0, str(SKILL_SCRIPTS))
import feishu_sheet as fs  # noqa: E402


class A:
    env_file = None
    sheet_id = None


def main():
    _, access, ss, sid = fs.connect(A())
    vals = fs.read_range(ss, access, f"{sid}!A1:I5000")
    rows = []
    for i, row in enumerate(vals, start=1):
        row = list(row) + [""] * (9 - len(row))
        rows.append({"row": i, **{h: ("" if v is None else str(v)) for h, v in zip(fs.HEADERS, row)}})
    json.dump(rows, open("ledger_dump.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"rows={len(rows)} sheet={sid}")


if __name__ == "__main__":
    main()
