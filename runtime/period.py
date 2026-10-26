"""报告的时间区间与文件标签。"""

from __future__ import annotations

import calendar
from datetime import date, timedelta

KINDS = ("daily", "weekly", "monthly", "review")

_QUARTERS = ((1, 3), (4, 6), (7, 9), (10, 12))


def period_range(
    kind: str,
    anchor: date | None = None,
    start: date | None = None,
    end: date | None = None,
) -> tuple[date, date]:
    if kind not in KINDS:
        raise ValueError(f"未知报告类型 {kind}")

    if kind == "review":
        if start is None or end is None:
            raise ValueError("review 需要同时提供 start 与 end")
        if end < start:
            raise ValueError(f"结束日期 {end} 早于开始日期 {start}")
        return start, end

    anchor = anchor or date.today()
    if kind == "daily":
        return anchor, anchor

    if kind == "weekly":
        first = anchor - timedelta(days=anchor.weekday())
        return first, first + timedelta(days=6)

    last_day = calendar.monthrange(anchor.year, anchor.month)[1]
    return date(anchor.year, anchor.month, 1), date(anchor.year, anchor.month, last_day)


def period_label(kind: str, start: date, end: date) -> str:
    if kind == "daily":
        return f"{start:%Y-%m-%d}-daily"
    if kind == "weekly":
        year, week, _ = start.isocalendar()
        return f"{year}-W{week:02d}-weekly"
    if kind == "monthly":
        return f"{start:%Y-%m}-monthly"

    quarter = _quarter(start, end)
    if quarter:
        return f"{start.year}-Q{quarter}-review"
    return f"{start:%Y-%m-%d}_{end:%Y-%m-%d}-review"


def _quarter(start: date, end: date) -> int | None:
    if start.year != end.year:
        return None
    for number, (first_month, last_month) in enumerate(_QUARTERS, start=1):
        quarter_start = date(start.year, first_month, 1)
        quarter_end = date(start.year, last_month, calendar.monthrange(start.year, last_month)[1])
        if start == quarter_start and end == quarter_end:
            return number
    return None
