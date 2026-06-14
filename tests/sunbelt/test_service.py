"""Tests for the read-side service: finished-job detection + discrepancy flags."""
from datetime import date, timedelta
from decimal import Decimal

from app.models import SunbeltRental
from app.brain.sunbelt.service import finished_jobs_set, compute_discrepancies


def _flag_types(flags):
    return {f["type"] for f in flags}


def test_finished_jobs_set(app, seed_jobs):
    finished = finished_jobs_set()
    # 530: only release is archived; 490: submittal-only, all Closed.
    assert 530 in finished
    assert 490 in finished
    # 480 and 170 are active fabrication jobs.
    assert 480 not in finished
    assert 170 not in finished


def test_overdue_flag():
    today = date(2026, 6, 14)
    r = SunbeltRental(
        matched_job_number=170,
        est_return_date=date(2025, 10, 1),  # long past
        billed_through=date(2026, 6, 10),   # still billing
        date_rented=date(2025, 9, 3),
        week_rate=Decimal("915.00"),
    )
    flags = compute_discrepancies(r, today, finished_jobs=set(), thresholds=(12000, 150))
    assert "overdue" in _flag_types(flags)


def test_not_overdue_when_return_in_future():
    today = date(2026, 6, 14)
    r = SunbeltRental(
        matched_job_number=480,
        est_return_date=today + timedelta(days=10),
        date_rented=today - timedelta(days=5),
        week_rate=Decimal("415.00"),
    )
    flags = compute_discrepancies(r, today, finished_jobs=set(), thresholds=(12000, 150))
    assert "overdue" not in _flag_types(flags)


def test_on_finished_job_flag():
    today = date(2026, 6, 14)
    r = SunbeltRental(
        matched_job_number=530,
        est_return_date=today + timedelta(days=30),
        date_rented=today - timedelta(days=10),
        week_rate=Decimal("295.00"),
    )
    flags = compute_discrepancies(r, today, finished_jobs={530}, thresholds=(12000, 150))
    assert "on_finished_job" in _flag_types(flags)


def test_cost_outlier_by_duration():
    today = date(2026, 6, 14)
    r = SunbeltRental(
        matched_job_number=170,
        est_return_date=today + timedelta(days=30),
        date_rented=today - timedelta(days=200),  # > 150-day threshold
        week_rate=Decimal("100.00"),
    )
    flags = compute_discrepancies(r, today, finished_jobs=set(), thresholds=(99999999, 150))
    assert "cost_outlier" in _flag_types(flags)


def test_no_flags_for_healthy_rental():
    today = date(2026, 6, 14)
    r = SunbeltRental(
        matched_job_number=480,
        est_return_date=today + timedelta(days=20),
        date_rented=today - timedelta(days=14),
        week_rate=Decimal("415.00"),
    )
    flags = compute_discrepancies(r, today, finished_jobs=set(), thresholds=(12000, 150))
    assert flags == []
