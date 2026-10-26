from datetime import date

import pytest

from runtime.period import period_label, period_range


def test_daily_range_is_the_anchor_day():
    assert period_range("daily", anchor=date(2026, 10, 26)) == (date(2026, 10, 26), date(2026, 10, 26))


def test_weekly_range_starts_monday():
    assert period_range("weekly", anchor=date(2026, 10, 26)) == (date(2026, 10, 26), date(2026, 11, 1))


def test_weekly_range_on_sunday_stays_in_same_week():
    assert period_range("weekly", anchor=date(2026, 11, 1)) == (date(2026, 10, 26), date(2026, 11, 1))


def test_monthly_range_covers_whole_month():
    assert period_range("monthly", anchor=date(2026, 2, 10)) == (date(2026, 2, 1), date(2026, 2, 28))


def test_review_requires_both_ends():
    with pytest.raises(ValueError, match="start"):
        period_range("review", start=date(2026, 7, 1))


def test_review_rejects_reversed_range():
    with pytest.raises(ValueError, match="早于"):
        period_range("review", start=date(2026, 9, 30), end=date(2026, 7, 1))


def test_labels():
    assert period_label("daily", date(2026, 10, 26), date(2026, 10, 26)) == "2026-10-26-daily"
    assert period_label("weekly", date(2026, 10, 26), date(2026, 11, 1)) == "2026-W44-weekly"
    assert period_label("monthly", date(2026, 10, 1), date(2026, 10, 31)) == "2026-10-monthly"
    assert period_label("review", date(2026, 7, 1), date(2026, 9, 30)) == "2026-Q3-review"
    assert period_label("review", date(2026, 1, 1), date(2026, 6, 30)) == "2026-01-01_2026-06-30-review"


def test_unknown_kind_raises():
    with pytest.raises(ValueError, match="未知报告类型"):
        period_range("yearly")
