"""
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
    """Sum remaining installation hours across all jobs.

    remaining = Install HRS * (1 - job_comp_fraction)
    """
    total = 0.0
    for job in jobs:
        install_hrs = job.get('Install HRS') or 0
        comp = _parse_job_comp(job.get('Job Comp'))
        try:
            total += float(install_hrs) * (1.0 - comp)
        except (ValueError, TypeError):
            pass
    return total
