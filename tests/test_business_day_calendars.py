"""N4 two-calendar business-day math: shop Mon–Thu vs field Mon–Fri."""
from datetime import date

import pytest

from app.trello.utils import (
    CALENDAR_FIELD,
    CALENDAR_SHOP,
    add_business_days,
    calculate_business_days_before,
    is_business_day,
)


# 2026-08-07 is a Friday; 2026-08-10 is a Monday.
FRI = date(2026, 8, 7)
MON = date(2026, 8, 10)
THU = date(2026, 8, 6)
WED = date(2026, 8, 5)


def test_is_business_day_field_includes_friday():
    assert is_business_day(FRI, calendar=CALENDAR_FIELD) is True
    assert is_business_day(MON, calendar=CALENDAR_FIELD) is True
    assert is_business_day(date(2026, 8, 8), calendar=CALENDAR_FIELD) is False  # Sat
    assert is_business_day(date(2026, 8, 9), calendar=CALENDAR_FIELD) is False  # Sun


def test_is_business_day_shop_excludes_friday():
    assert is_business_day(FRI, calendar=CALENDAR_SHOP) is False
    assert is_business_day(THU, calendar=CALENDAR_SHOP) is True
    assert is_business_day(MON, calendar=CALENDAR_SHOP) is True
    assert is_business_day(date(2026, 8, 8), calendar=CALENDAR_SHOP) is False


def test_unknown_calendar_raises():
    with pytest.raises(ValueError, match="unknown calendar"):
        is_business_day(MON, calendar="holiday")


def test_add_business_days_field_counts_friday():
    # Exclusive of start (legacy Excel / field contract): Mon + 4 field days =
    # Tue, Wed, Thu, Fri → 2026-08-14.
    assert add_business_days(MON, 4, calendar=CALENDAR_FIELD) == date(2026, 8, 14)


def test_add_business_days_shop_skips_friday():
    # Exclusive of start — same contract as field, different working set.
    # Thu + 1 shop day: skip Fri/Sat/Sun → next Mon.
    assert add_business_days(THU, 1, calendar=CALENDAR_SHOP) == MON

    # Mon + 4 shop days = one full shop week of capacity (~400 hrs @ ~100/day).
    # Counted days: Tue, Wed, Thu, next Mon — Friday is NOT a shop day.
    # Landing on Thu (8/13) would be wrong: that is only *three* exclusive shop
    # steps (Tue/Wed/Thu), or an inclusive Mon–Thu span the helper does not use.
    assert add_business_days(MON, 4, calendar=CALENDAR_SHOP) == date(2026, 8, 17)

    # Parity check: field's 5th day is Friday; shop never lands there.
    assert add_business_days(MON, 5, calendar=CALENDAR_FIELD) == date(2026, 8, 17)  # next Mon
    assert add_business_days(MON, 5, calendar=CALENDAR_SHOP) == date(2026, 8, 18)   # next Tue


def test_before_shop_skips_friday_backward():
    # 1 shop day before Monday = Thursday (not Friday)
    assert calculate_business_days_before(MON, 1, calendar=CALENDAR_SHOP) == THU
    # Field still lands on Friday
    assert calculate_business_days_before(MON, 1, calendar=CALENDAR_FIELD) == FRI


def test_default_calendar_is_field():
    # Default stays Mon–Fri for backward compatibility
    assert add_business_days(THU, 1) == FRI
    assert calculate_business_days_before(MON, 1) == FRI


def test_zero_business_days_is_noop():
    assert add_business_days(FRI, 0, calendar=CALENDAR_SHOP) == FRI
    assert calculate_business_days_before(FRI, 0, calendar=CALENDAR_SHOP) == FRI


def test_paint_window_style_chain_never_starts_on_friday():
    """Lookahead paint: 3 shop days ending shop-day-before ship (field Fri)."""
    ship = FRI  # field ship day before Mon install
    paint_end = calculate_business_days_before(ship, 1, calendar=CALENDAR_SHOP)
    paint_start = calculate_business_days_before(ship, 3, calendar=CALENDAR_SHOP)
    assert paint_end == THU
    # 3 shop days before Fri: Thu, Wed, Tue → start Tue
    assert paint_start == date(2026, 8, 4)
    assert paint_start.weekday() < 4
    assert paint_end.weekday() < 4


def test_fab_projection_uses_shop_calendar():
    from app.brain.job_log.scheduling.calculator import calculate_projected_fab_complete_date

    # days_in_front=0 → complete "today" (reference), even if today is Friday.
    assert calculate_projected_fab_complete_date(0, FRI) == FRI
    # 1 day of queue ahead of Thursday → clears next shop day (Monday), not Friday.
    assert calculate_projected_fab_complete_date(1, THU) == MON
    # ~1 shop-week of queue (4 days @ FAB_HOURS_PER_DAY) from Monday → next Monday.
    assert calculate_projected_fab_complete_date(4, MON) == date(2026, 8, 17)
