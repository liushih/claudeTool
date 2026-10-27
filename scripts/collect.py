"""采集报告数据，输出结构化 JSON。"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from runtime import config  # noqa: E402
from runtime.gitlog import collect_git  # noqa: E402
from runtime.period import period_label, period_range  # noqa: E402
from runtime.report_config import ReportConfigError, load_report_config  # noqa: E402
from runtime.zentao import collect_zentao  # noqa: E402


def main(argv: list[str] | None = None, git_fn=None, zentao_fn=None) -> int:
    parser = argparse.ArgumentParser(description="采集报告数据")
    parser.add_argument("--project", required=True)
    parser.add_argument("--type", default="daily", choices=["daily", "weekly", "monthly", "review"])
    parser.add_argument("--anchor", help="锚点日期 YYYY-MM-DD，默认今天")
    parser.add_argument("--start", help="述职开始日期 YYYY-MM-DD")
    parser.add_argument("--end", help="述职结束日期 YYYY-MM-DD")
    parser.add_argument("--out", help="输出 JSON 路径")
    args = parser.parse_args(argv)

    try:
        start, end = period_range(
            args.type,
            anchor=date.fromisoformat(args.anchor) if args.anchor else None,
            start=date.fromisoformat(args.start) if args.start else None,
            end=date.fromisoformat(args.end) if args.end else None,
        )
    except ValueError as exc:
        parser.error(str(exc))

    try:
        cfg = load_report_config(args.project)
    except ReportConfigError as exc:
        print(exc, file=sys.stderr)
        return 2

    git_fn = git_fn or collect_git
    zentao_fn = zentao_fn or collect_zentao

    repos = git_fn(cfg.git.repos, cfg.git.authors, start, end)
    tasks, bugs, warnings = zentao_fn(cfg.zentao, start, end)

    # 只有采集本身失败才算数据缺失；「缺少完成人」这类属于提醒，不影响完整性
    fatal = [w for w in warnings if "失败" in w or w.startswith("禅道未配置")]
    label = period_label(args.type, start, end)
    data = {
        "project": args.project,
        "period": {"type": args.type, "start": start.isoformat(), "end": end.isoformat()},
        "sources": {
            "git": "ok" if all(repo.status == "ok" for repo in repos) else "partial",
            "zentao": "ok" if not fatal else f"failed: {fatal[0]}",
        },
        "git": [asdict(repo) for repo in repos],
        "zentao": {"tasks": tasks, "bugs": bugs},
        "warnings": warnings,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    out = Path(args.out) if args.out else (
        config.data_home() / "reports" / args.project / ".collect" / f"{label}.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
