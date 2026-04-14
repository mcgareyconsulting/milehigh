"""
@milehigh-header
schema_version: 1
purpose: Compute aggregate KPI totals (remaining fab hours and remaining install hours) used by dashboard summaries and scheduling.
exports:
  get_fab_modifier: Return the remaining-work multiplier (0.0-1.0) for a fabrication stage
  calculate_total_fab_hrs: Sum remaining fab hours across all jobs using stage modifiers
  calculate_total_install_hrs: Sum remaining install hours for post-fabrication jobs only
imports_from: []
imported_by: [app/brain/job_log/scheduling/__init__.py]
invariants:
  - Only jobs with get_fab_modifier==0.0 are included in install hour totals
  - Job Comp values are capped at 1.0 to prevent negative remaining hours
  - Unknown stages default to modifier 1.0 (conservative)
updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)

Aggregate KPI helpers: total remaining fab hours and total remaining install hours.
"""

_FAB_MODIFIER_TABLE = {
    'Released': 1.0,
    'Cut Start': 0.9, 'Cut start': 0.9,
    'Fit up Comp': 0.5, 'Fit Up Complete': 0.5, 'Fit Up Complete.': 0.5, 'Fitup comp': 0.5,
    'WeldingQC': 0.0, 'Welded QC': 0.0, 'Welding QC': 0.0, 'Welded': 0.0,
    'Paint Complete': 0.0, 'Paint complete': 0.0, 'Paint comp': 0.0,
    'Store': 0.0, 'Store at MHMW for shipping': 0.0,
    'Ship Planning': 0.0, 'Shipping planning': 0.0,
    'Ship Complete': 0.0, 'Shipping completed': 0.0,
    'Complete': 0.0,
}


def get_fab_modifier(stage: str) -> float:
    """Return the remaining-work multiplier for a fabrication stage.

    Unknown stages default to 1.0 (conservative).
    """
    return _FAB_MODIFIER_TABLE.get(stage, 1.0)


def _parse_job_comp(value) -> float:
    """Parse a Job Comp value to a 0–1 fraction, capped at 1.0.

    0.75 → 0.75, 1.0 → 1.0, None/'' → 0.0, 1.5 → 1.0.
    """
    if value is None:
        return 0.0
    try:
        frac = float(value)
    except (ValueError, TypeError):
        return 0.0
    return min(frac, 1.0)


def calculate_total_fab_hrs(jobs: list[dict]) -> float:
    """Sum remaining fabrication hours across all jobs.

    remaining = Fab Hrs * get_fab_modifier(Stage)
    """
    total = 0.0
    for job in jobs:
        fab_hrs = job.get('Fab Hrs') or 0
        stage = job.get('Stage') or ''
        try:
            total += float(fab_hrs) * get_fab_modifier(stage)
        except (ValueError, TypeError):
            pass
    return total


def calculate_total_install_hrs(jobs: list[dict]) -> float:
    """Sum remaining installation hours across Welded-or-later jobs only.

    Only jobs where fabrication is complete (get_fab_modifier == 0.0) are included.
    remaining = Install HRS * (1 - job_comp_fraction)
    """
    total = 0.0
    for job in jobs:
        stage = job.get('Stage') or ''
        if get_fab_modifier(stage) > 0.0:
            continue  # still in fabrication — exclude from install planning
        install_hrs = job.get('Install HRS') or 0
        comp = _parse_job_comp(job.get('Job Comp'))
        try:
            total += float(install_hrs) * (1.0 - comp)
        except (ValueError, TypeError):
            pass
    return total
