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

    def test_cut_start_title_case(self):
        assert get_fab_modifier('Cut Start') == 0.9

    def test_cut_start_lower(self):
        assert get_fab_modifier('Cut start') == 0.9

    def test_fit_up_complete_dot(self):
        assert get_fab_modifier('Fit Up Complete.') == 0.5

    def test_fit_up_complete(self):
        assert get_fab_modifier('Fit Up Complete') == 0.5

    def test_welded_zero(self):
        assert get_fab_modifier('Welded') == 0.0

    def test_welded_qc_zero(self):
        assert get_fab_modifier('Welded QC') == 0.0

    def test_paint_complete_zero(self):
        assert get_fab_modifier('Paint complete') == 0.0

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

    def test_welded_contributes_zero(self):
        jobs = [{'Fab Hrs': 80, 'Stage': 'Welded', 'Install HRS': 0, 'Job Comp': 0.0}]
        assert calculate_total_fab_hrs(jobs) == pytest.approx(0.0)

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
            {'Fab Hrs': 120, 'Stage': 'Fit Up Complete'}, # 120 * 0.5 = 60
            {'Fab Hrs': 80,  'Stage': 'Welded'},          # 80  * 0.0 = 0
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
    def test_zero_comp_full_hours(self):
        jobs = [{'Install HRS': 50, 'Job Comp': 0.0, 'Stage': 'Welded'}]
        assert calculate_total_install_hrs(jobs) == pytest.approx(50.0)

    def test_full_comp_zero_remaining(self):
        jobs = [{'Install HRS': 50, 'Job Comp': 1.0, 'Stage': 'Welded'}]
        assert calculate_total_install_hrs(jobs) == pytest.approx(0.0)

    def test_partial_comp(self):
        jobs = [{'Install HRS': 100, 'Job Comp': 0.75, 'Stage': 'Paint Complete'}]
        assert calculate_total_install_hrs(jobs) == pytest.approx(25.0)

    def test_multi_job_sum(self):
        jobs = [
            {'Install HRS': 100, 'Job Comp': 0.0, 'Stage': 'Welded'},        # 100 * 1.0 = 100
            {'Install HRS': 80,  'Job Comp': 0.5, 'Stage': 'Ship Planning'},  # 80  * 0.5 = 40
            {'Install HRS': 60,  'Job Comp': 1.0, 'Stage': 'Complete'},       # 60  * 0.0 = 0
        ]
        assert calculate_total_install_hrs(jobs) == pytest.approx(140.0)

    def test_missing_install_hrs_treated_as_zero(self):
        jobs = [{'Job Comp': '0', 'Stage': 'Welded'}]
        assert calculate_total_install_hrs(jobs) == pytest.approx(0.0)

    def test_null_job_comp_treated_as_zero(self):
        jobs = [{'Install HRS': 40, 'Job Comp': None, 'Stage': 'Ship Complete'}]
        assert calculate_total_install_hrs(jobs) == pytest.approx(40.0)

    def test_empty_list(self):
        assert calculate_total_install_hrs([]) == pytest.approx(0.0)

    def test_pre_welded_stages_excluded(self):
        jobs = [
            {'Install HRS': 100, 'Job Comp': 0.0, 'Stage': 'Released'},
            {'Install HRS': 80,  'Job Comp': 0.0, 'Stage': 'Cut Start'},
            {'Install HRS': 60,  'Job Comp': 0.0, 'Stage': 'Fit Up Complete'},
        ]
        assert calculate_total_install_hrs(jobs) == pytest.approx(0.0)

    def test_unknown_stage_excluded(self):
        jobs = [{'Install HRS': 50, 'Job Comp': 0.0, 'Stage': 'Some Unknown Stage'}]
        assert calculate_total_install_hrs(jobs) == pytest.approx(0.0)

    def test_mixed_stages_only_welded_or_later_count(self):
        jobs = [
            {'Install HRS': 100, 'Job Comp': 0.0, 'Stage': 'Released'},       # excluded
            {'Install HRS': 80,  'Job Comp': 0.0, 'Stage': 'Cut Start'},      # excluded
            {'Install HRS': 60,  'Job Comp': 0.0, 'Stage': 'Welded'},         # 60 * 1.0 = 60
            {'Install HRS': 40,  'Job Comp': 0.5, 'Stage': 'Paint Complete'}, # 40 * 0.5 = 20
        ]
        assert calculate_total_install_hrs(jobs) == pytest.approx(80.0)
