"""Tests for start install cascade — red date protection and formula updates."""

import pytest
from datetime import date
from unittest.mock import MagicMock, patch

from app.brain.job_log.scheduling.calculator import (
    calculate_all_job_scheduling,
    calculate_hours_in_front,
    calculate_remaining_fab_hours,
)


class TestRedDateProtection:
    """Verify that hard-date (red date) releases are not overwritten by the cascade."""

    def _make_mock_release(self, job, release, fab_hrs, stage, fab_order,
                           start_install=None, comp_eta=None,
                           start_install_formulaTF=None):
        rec = MagicMock()
        rec.job = job
        rec.release = release
        rec.fab_hrs = fab_hrs
        rec.install_hrs = 40.0
        rec.stage = stage
        rec.fab_order = fab_order
        rec.start_install = start_install
        rec.comp_eta = comp_eta
        rec.start_install_formulaTF = start_install_formulaTF
        rec.source_of_update = None
        rec.last_updated_at = None
        return rec

    @patch('app.brain.job_log.scheduling.service.Releases')
    @patch('app.brain.job_log.scheduling.service.db')
    def test_red_date_not_overwritten(self, mock_db, mock_releases):
        from app.brain.job_log.scheduling.service import recalculate_all_jobs_scheduling

        hard_date = date(2026, 6, 15)
        releases = [
            self._make_mock_release(100, 'A', 80.0, 'Released', 3,
                                    start_install=hard_date, comp_eta=date(2026, 7, 1),
                                    start_install_formulaTF=False),
            self._make_mock_release(100, 'B', 60.0, 'Cut start', 4,
                                    start_install=None, comp_eta=None,
                                    start_install_formulaTF=True),
        ]
        mock_releases.query.all.return_value = releases

        result = recalculate_all_jobs_scheduling(reference_date=date(2026, 4, 1))

        # Hard date release should be untouched
        assert releases[0].start_install == hard_date
        assert releases[0].comp_eta == date(2026, 7, 1)

        # Formula release should be updated (not None anymore)
        assert releases[1].start_install is not None
        assert releases[1].comp_eta is not None

    @patch('app.brain.job_log.scheduling.service.Releases')
    @patch('app.brain.job_log.scheduling.service.db')
    def test_formula_date_is_updated(self, mock_db, mock_releases):
        from app.brain.job_log.scheduling.service import recalculate_all_jobs_scheduling

        old_date = date(2026, 1, 1)
        releases = [
            self._make_mock_release(100, 'A', 80.0, 'Released', 3,
                                    start_install=old_date, comp_eta=old_date,
                                    start_install_formulaTF=True),
        ]
        mock_releases.query.all.return_value = releases

        result = recalculate_all_jobs_scheduling(reference_date=date(2026, 4, 1))

        # Formula-driven date should be recalculated (different from old stale value)
        assert releases[0].start_install != old_date

    @patch('app.brain.job_log.scheduling.service.Releases')
    @patch('app.brain.job_log.scheduling.service.db')
    def test_none_formulaTF_treated_as_formula(self, mock_db, mock_releases):
        """start_install_formulaTF=None (unset) should be treated as formula-driven."""
        from app.brain.job_log.scheduling.service import recalculate_all_jobs_scheduling

        releases = [
            self._make_mock_release(100, 'A', 80.0, 'Released', 3,
                                    start_install=None, comp_eta=None,
                                    start_install_formulaTF=None),
        ]
        mock_releases.query.all.return_value = releases

        recalculate_all_jobs_scheduling(reference_date=date(2026, 4, 1))

        # Should be updated (not skipped)
        assert releases[0].start_install is not None


class TestHoldReleaseCascade:
    """Hold releases should receive full hours and cascade normally."""

    def test_hold_gets_full_remaining_hours(self):
        """A Hold release should retain 100% of its fab hours."""
        remaining = calculate_remaining_fab_hours(80.0, 'Hold')
        assert remaining == pytest.approx(80.0)

    def test_hold_release_gets_calculated_dates(self):
        """A Hold release should get start_install and comp_eta, not None."""
        jobs = [
            {'fab_hrs': 80.0, 'install_hrs': 40.0, 'stage': 'Released', 'fab_order': 1},
            {'fab_hrs': 60.0, 'install_hrs': 30.0, 'stage': 'Hold', 'fab_order': 2},
        ]
        results = calculate_all_job_scheduling(jobs, reference_date=date(2026, 4, 1))

        # Hold release should have calculated dates, not None
        assert results[1]['install_start_date'] is not None
        assert results[1]['install_complete_date'] is not None

    def test_hold_hours_included_in_cascade(self):
        """Releases after a Hold release should include its full hours in hours_in_front."""
        jobs = [
            {'fab_hrs': 80.0, 'install_hrs': 40.0, 'stage': 'Released', 'fab_order': 1},
            {'fab_hrs': 60.0, 'install_hrs': 30.0, 'stage': 'Hold', 'fab_order': 2},
            {'fab_hrs': 40.0, 'install_hrs': 20.0, 'stage': 'Cut Start', 'fab_order': 3},
        ]
        results = calculate_all_job_scheduling(jobs, reference_date=date(2026, 4, 1))

        # Third release should have Released (80) + Hold (60) hours in front
        assert results[2]['hours_in_front'] == pytest.approx(80.0 + 60.0)

    @patch('app.brain.job_log.scheduling.service.Releases')
    @patch('app.brain.job_log.scheduling.service.db')
    def test_hold_release_not_cleared_in_batch(self, mock_db, mock_releases):
        """recalculate_all_jobs_scheduling should set dates on Hold releases, not clear them."""
        from app.brain.job_log.scheduling.service import recalculate_all_jobs_scheduling

        rec = MagicMock()
        rec.job = 100
        rec.release = 'A'
        rec.fab_hrs = 80.0
        rec.install_hrs = 40.0
        rec.stage = 'Hold'
        rec.fab_order = 1.0
        rec.start_install = None
        rec.comp_eta = None
        rec.start_install_formulaTF = True
        rec.source_of_update = None
        rec.last_updated_at = None

        mock_releases.query.all.return_value = [rec]

        recalculate_all_jobs_scheduling(reference_date=date(2026, 4, 1))

        assert rec.start_install is not None
        assert rec.comp_eta is not None


class TestRedDateContributesToQueue:
    """Red-date releases must still contribute remaining fab hours to the queue."""

    def test_red_date_hours_in_front(self):
        """A hard-date release's fab hours should count in hours_in_front for later releases."""
        jobs = [
            {'fab_hrs': 100.0, 'stage': 'Released', 'fab_order': 3,
             'remaining_fab_hours': calculate_remaining_fab_hours(100.0, 'Released')},
            {'fab_hrs': 60.0, 'stage': 'Cut start', 'fab_order': 4,
             'remaining_fab_hours': calculate_remaining_fab_hours(60.0, 'Cut start')},
        ]

        # Release B (fab_order=4) should have Release A's hours in front
        hours = calculate_hours_in_front(4, jobs)
        assert hours == pytest.approx(100.0)  # 100 * 1.0 (Released)

    def test_full_cascade_includes_all_releases(self):
        """calculate_all_job_scheduling should include all releases in queue math."""
        jobs = [
            {'fab_hrs': 80.0, 'install_hrs': 40.0, 'stage': 'Released', 'fab_order': 3},
            {'fab_hrs': 60.0, 'install_hrs': 30.0, 'stage': 'Cut start', 'fab_order': 4},
            {'fab_hrs': 40.0, 'install_hrs': 20.0, 'stage': 'Fit Up Complete', 'fab_order': 5},
        ]

        results = calculate_all_job_scheduling(jobs, reference_date=date(2026, 4, 1))

        # First release has 0 hours in front
        assert results[0]['hours_in_front'] == pytest.approx(0.0)
        # Second release has first release's remaining hours in front
        assert results[1]['hours_in_front'] == pytest.approx(80.0)  # 80 * 1.0
        # Third has first + second in front
        assert results[2]['hours_in_front'] == pytest.approx(80.0 + 54.0)  # 80*1.0 + 60*0.9


class TestDefaultFabOrderSentinel:
    """Releases with the DEFAULT_FAB_ORDER sentinel (80.555) — meaning no explicit fab_order
    has been assigned — must still fully participate in queue calculations so the projected
    run-out reflects their hours, and they must cascade through each other in some stable
    order rather than collapsing onto a single date."""

    def test_sentinel_release_contributes_to_later_releases(self):
        from app.api.helpers import DEFAULT_FAB_ORDER

        # A release with a higher explicit fab_order should still see the sentinel release
        # as in front of it — its remaining hours count toward the run-out.
        jobs = [
            {'fab_hrs': 60.0, 'install_hrs': 30.0, 'stage': 'Released', 'fab_order': DEFAULT_FAB_ORDER},
            {'fab_hrs': 40.0, 'install_hrs': 20.0, 'stage': 'Released', 'fab_order': 100},
        ]
        results = calculate_all_job_scheduling(jobs, reference_date=date(2026, 4, 1))

        assert results[1]['hours_in_front'] == pytest.approx(60.0)

    def test_multiple_sentinel_releases_cascade_through_each_other(self):
        from app.api.helpers import DEFAULT_FAB_ORDER

        # Three sentinel releases must cascade in list order, each with strictly more
        # hours-in-front than the previous, so the run-out reflects their cumulative time.
        jobs = [
            {'fab_hrs': 80.0, 'install_hrs': 40.0, 'stage': 'Released', 'fab_order': 5},
            {'fab_hrs': 60.0, 'install_hrs': 30.0, 'stage': 'Released', 'fab_order': DEFAULT_FAB_ORDER},
            {'fab_hrs': 40.0, 'install_hrs': 20.0, 'stage': 'Released', 'fab_order': DEFAULT_FAB_ORDER},
            {'fab_hrs': 20.0, 'install_hrs': 10.0, 'stage': 'Released', 'fab_order': DEFAULT_FAB_ORDER},
        ]
        results = calculate_all_job_scheduling(jobs, reference_date=date(2026, 4, 1))

        # First sentinel sees only the explicit-order release in front (80h).
        assert results[1]['hours_in_front'] == pytest.approx(80.0)
        # Second sentinel adds the first sentinel's 60h.
        assert results[2]['hours_in_front'] == pytest.approx(80.0 + 60.0)
        # Third sentinel adds the first and second sentinels' 60h + 40h.
        assert results[3]['hours_in_front'] == pytest.approx(80.0 + 60.0 + 40.0)

        # All three sentinel releases must produce valid install dates (cascade does not stall).
        for idx in (1, 2, 3):
            assert results[idx]['install_start_date'] is not None
            assert results[idx]['install_complete_date'] is not None

    def test_sentinel_release_run_out_includes_all_work(self):
        from app.api.helpers import DEFAULT_FAB_ORDER

        # The last release in the queue (a sentinel) should reflect the cumulative
        # remaining hours of every other non-hard-date release in the queue.
        jobs = [
            {'fab_hrs': 80.0, 'install_hrs': 40.0, 'stage': 'Released', 'fab_order': 5},
            {'fab_hrs': 100.0, 'install_hrs': 50.0, 'stage': 'Released', 'fab_order': 10},
            {'fab_hrs': 60.0, 'install_hrs': 30.0, 'stage': 'Released', 'fab_order': DEFAULT_FAB_ORDER},
            {'fab_hrs': 40.0, 'install_hrs': 20.0, 'stage': 'Released', 'fab_order': DEFAULT_FAB_ORDER},
        ]
        results = calculate_all_job_scheduling(jobs, reference_date=date(2026, 4, 1))

        # The final sentinel sees: both explicit-order releases + the first sentinel.
        assert results[3]['hours_in_front'] == pytest.approx(80.0 + 100.0 + 60.0)
