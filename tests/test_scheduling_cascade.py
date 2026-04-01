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
