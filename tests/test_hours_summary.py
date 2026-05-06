"""Tests for hours_summary KPI helpers."""

import pytest
from app.brain.job_log.scheduling.hours_summary import (
    get_fab_modifier,
    _parse_job_comp,
    calculate_total_fab_hrs,
    calculate_total_install_hrs,
)


# ---------------------------------------------------------------------------
# get_fab_modifier
# ---------------------------------------------------------------------------

class TestGetFabModifier:
    def test_released(self):
        assert get_fab_modifier('Released') == 1.0

    def test_cut_start(self):
        assert get_fab_modifier('Cut Start') == 0.9

    def test_fitup_complete(self):
        assert get_fab_modifier('Fitup Complete') == 0.5

    def test_welded_qc_zero(self):
        assert get_fab_modifier('Welded QC') == 0.0

    def test_paint_complete_zero(self):
        assert get_fab_modifier('Paint Complete') == 0.0

    def test_install_start_zero(self):
        # Past fab — install_start is included in install hour planning, not fab
        assert get_fab_modifier('Install Start') == 0.0

    def test_install_complete_zero(self):
        assert get_fab_modifier('Install Complete') == 0.0

    def test_complete_zero(self):
        assert get_fab_modifier('Complete') == 0.0

    def test_unknown_stage_conservative(self):
        assert get_fab_modifier('Some Unknown Stage') == 1.0

    def test_empty_string_conservative(self):
        assert get_fab_modifier('') == 1.0


# ---------------------------------------------------------------------------
# _parse_job_comp
# ---------------------------------------------------------------------------

class TestParseJobComp:
    def test_seventy_five_pct(self):
        assert _parse_job_comp(0.75) == pytest.approx(0.75)

    def test_one(self):
        assert _parse_job_comp(1.0) == pytest.approx(1.0)

    def test_zero(self):
        assert _parse_job_comp(0.0) == pytest.approx(0.0)

    def test_empty_string(self):
        assert _parse_job_comp('') == pytest.approx(0.0)

    def test_none(self):
        assert _parse_job_comp(None) == pytest.approx(0.0)

    def test_over_1_capped(self):
        assert _parse_job_comp(1.5) == pytest.approx(1.0)

    def test_string_fraction(self):
        assert _parse_job_comp('0.5') == pytest.approx(0.5)

    def test_nine_tenths(self):
        assert _parse_job_comp(0.9) == pytest.approx(0.9)


# ---------------------------------------------------------------------------
# calculate_total_fab_hrs
# ---------------------------------------------------------------------------

class TestCalculateTotalFabHrs:
    def test_single_released_job(self):
        jobs = [{'Fab Hrs': 100, 'Stage': 'Released', 'Install HRS': 0, 'Job Comp': 0.0}]
        assert calculate_total_fab_hrs(jobs) == pytest.approx(100.0)

    def test_welded_qc_contributes_zero(self):
        jobs = [{'Fab Hrs': 80, 'Stage': 'Welded QC', 'Install HRS': 0, 'Job Comp': 0.0}]
        assert calculate_total_fab_hrs(jobs) == pytest.approx(0.0)

    def test_unknown_stage_full_hours(self):
        jobs = [{'Fab Hrs': 50, 'Stage': 'Mystery Stage', 'Install HRS': 0, 'Job Comp': '0'}]
        assert calculate_total_fab_hrs(jobs) == pytest.approx(50.0)

    def test_multi_job_sum(self):
        jobs = [
            {'Fab Hrs': 100, 'Stage': 'Released'},       # 100 * 1.0 = 100
            {'Fab Hrs': 200, 'Stage': 'Cut Start'},       # 200 * 0.9 = 180
            {'Fab Hrs': 120, 'Stage': 'Fitup Complete'},  # 120 * 0.5 = 60
            {'Fab Hrs': 80,  'Stage': 'Welded QC'},       # 80  * 0.0 = 0
        ]
        assert calculate_total_fab_hrs(jobs) == pytest.approx(340.0)

    def test_missing_fab_hrs_treated_as_zero(self):
        jobs = [{'Stage': 'Released'}]
        assert calculate_total_fab_hrs(jobs) == pytest.approx(0.0)

    def test_null_fab_hrs_treated_as_zero(self):
        jobs = [{'Fab Hrs': None, 'Stage': 'Released'}]
        assert calculate_total_fab_hrs(jobs) == pytest.approx(0.0)

    def test_empty_list(self):
        assert calculate_total_fab_hrs([]) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# calculate_total_install_hrs
# ---------------------------------------------------------------------------

class TestCalculateTotalInstallHrs:
    """Stage-driven install hour total. Job Comp does NOT factor in.

    Per STAGE_HOUR_PERCENTAGES (the client "Banana Code" matrix):
      Released → Fitup Complete   : install % = 0   (excluded)
      Weld Start → Ship Complete  : install % = 100 (full hours count)
      Install Start               : install % = 50  (half hours count)
      Install Complete, Complete  : install % = 0   (excluded)
    """

    def test_welded_qc_full_hours(self):
        jobs = [{'Install HRS': 50, 'Stage': 'Welded QC'}]
        assert calculate_total_install_hrs(jobs) == pytest.approx(50.0)

    def test_install_start_half_hours(self):
        # Install Start is 50% per the matrix.
        jobs = [{'Install HRS': 100, 'Stage': 'Install Start'}]
        assert calculate_total_install_hrs(jobs) == pytest.approx(50.0)

    def test_install_complete_zero(self):
        jobs = [{'Install HRS': 100, 'Stage': 'Install Complete'}]
        assert calculate_total_install_hrs(jobs) == pytest.approx(0.0)

    def test_complete_zero(self):
        jobs = [{'Install HRS': 100, 'Stage': 'Complete'}]
        assert calculate_total_install_hrs(jobs) == pytest.approx(0.0)

    def test_weld_start_now_counts(self):
        # Per matrix Weld Start = 100% install remaining; previously this was excluded
        # because the gate used fab-modifier==0 (Welded QC or later).
        jobs = [{'Install HRS': 80, 'Stage': 'Weld Start'}]
        assert calculate_total_install_hrs(jobs) == pytest.approx(80.0)

    def test_hold_full_hours(self):
        jobs = [{'Install HRS': 60, 'Stage': 'Hold'}]
        assert calculate_total_install_hrs(jobs) == pytest.approx(60.0)

    def test_job_comp_does_not_affect_total(self):
        # Job Comp is not part of the formula anymore; same stage + same Install HRS
        # must yield the same total regardless of Job Comp value.
        a = [{'Install HRS': 100, 'Job Comp': 0.0, 'Stage': 'Paint Complete'}]
        b = [{'Install HRS': 100, 'Job Comp': 0.75, 'Stage': 'Paint Complete'}]
        c = [{'Install HRS': 100, 'Job Comp': 'X',  'Stage': 'Paint Complete'}]
        assert calculate_total_install_hrs(a) == calculate_total_install_hrs(b)
        assert calculate_total_install_hrs(b) == calculate_total_install_hrs(c)

    def test_multi_job_sum(self):
        jobs = [
            {'Install HRS': 100, 'Stage': 'Welded QC'},        # 100 * 1.0  = 100
            {'Install HRS': 80,  'Stage': 'Ship Planning'},    #  80 * 1.0  =  80
            {'Install HRS': 40,  'Stage': 'Install Start'},    #  40 * 0.5  =  20
            {'Install HRS': 60,  'Stage': 'Complete'},         #  60 * 0.0  =   0
        ]
        assert calculate_total_install_hrs(jobs) == pytest.approx(200.0)

    def test_missing_install_hrs_treated_as_zero(self):
        jobs = [{'Stage': 'Welded QC'}]
        assert calculate_total_install_hrs(jobs) == pytest.approx(0.0)

    def test_empty_list(self):
        assert calculate_total_install_hrs([]) == pytest.approx(0.0)

    def test_pre_weld_start_stages_excluded(self):
        jobs = [
            {'Install HRS': 100, 'Stage': 'Released'},
            {'Install HRS': 80,  'Stage': 'Cut Start'},
            {'Install HRS': 60,  'Stage': 'Fitup Complete'},
        ]
        assert calculate_total_install_hrs(jobs) == pytest.approx(0.0)

    def test_unknown_stage_excluded(self):
        jobs = [{'Install HRS': 50, 'Stage': 'Some Unknown Stage'}]
        assert calculate_total_install_hrs(jobs) == pytest.approx(0.0)
