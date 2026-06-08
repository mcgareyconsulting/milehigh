"""Unit tests for the unified num_guys-based comp_eta formula.

install_days = ceil(install_hrs / (num_guys * 8)); comp_eta is the LAST working day of
the install — start + (install_days - 1) business days — so a 1-day install completes the
day it starts. num_guys defaults to 2 (2 * 8 = 16), reproducing the legacy fixed capacity.
"""
from datetime import date

from app.brain.job_log.scheduling.calculator import calculate_install_complete_date


# 2026-06-15 is a Monday; 2026-06-18 is a Thursday.
MON = date(2026, 6, 15)
THU = date(2026, 6, 18)


def test_default_num_guys_matches_legacy_16():
    # num_guys=None must reproduce num_guys=2 (the legacy /16 capacity).
    assert calculate_install_complete_date(MON, 32.0, None) == calculate_install_complete_date(MON, 32.0, 2.0)


def test_two_guys_two_business_days():
    # 32 / (2*8) = 2 install days; last working day = Mon + 1 -> Tue 2026-06-16
    assert calculate_install_complete_date(MON, 32.0, 2.0) == date(2026, 6, 16)


def test_more_guys_is_shorter():
    # 4 guys: 32 / 32 = 1 install day; completes the day it starts -> Mon 2026-06-15
    assert calculate_install_complete_date(MON, 32.0, 4.0) == date(2026, 6, 15)


def test_one_guy_is_longer():
    # 1 guy: 32 / 8 = 4 install days; last working day = Mon + 3 -> Thu 2026-06-18
    assert calculate_install_complete_date(MON, 32.0, 1.0) == date(2026, 6, 18)


def test_weekend_rollover():
    # Thu + ceil(48/16)=3 install days; last working day = Thu + 2: Fri, Mon -> 2026-06-22
    assert calculate_install_complete_date(THU, 48.0, 2.0) == date(2026, 6, 22)


def test_zero_hours_is_same_day():
    assert calculate_install_complete_date(MON, 0.0, 2.0) == MON


def test_one_day_install_completes_same_day():
    # The 222-333 case: 12 hrs / (2*8) = ceil(0.75) = 1 install day -> completes the start day.
    assert calculate_install_complete_date(date(2026, 6, 12), 12.0, 2.0) == date(2026, 6, 12)


def test_none_inputs_return_none():
    assert calculate_install_complete_date(None, 32.0, 2.0) is None
    assert calculate_install_complete_date(MON, None, 2.0) is None
    assert calculate_install_complete_date(MON, -1.0, 2.0) is None


def test_invalid_num_guys_falls_back_to_default():
    # 0 / negative num_guys -> default 2.
    assert calculate_install_complete_date(MON, 32.0, 0) == calculate_install_complete_date(MON, 32.0, 2.0)
