/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Shared fab-hours stage modifier + total computation, reused by the
 *   Job Log KPI (useJobsFilters.js) and the DWL header figure.
 * exports:
 *   FAB_MODIFIER: per-stage multiplier applied to a release's Fab Hrs
 *   getFabModifier: lookup with default 1.0 for unknown stages
 *   computeTotalFabHrs: sum of (Fab Hrs * modifier) over a jobs array
 * invariants:
 *   - Mirrors app.api.helpers.STAGE_HOUR_PERCENTAGES["fab"] / 100 (Banana Code).
 *   - Backend SQL CASE in /brain/fab-hours-total and get_fab_modifier() must match.
 *   - Unknown stages default to 1.0 (conservative).
 * updated_by_agent: 2026-08-06T00:00:00Z
 */

/** Remaining-fab multiplier per stage (1.0 = full Fab Hrs still in the total). */
export const FAB_MODIFIER = {
    'Released':         1.0,
    'Material Ordered': 1.0,
    'Cut Start':        0.9,
    'Cut Complete':     0.9,
    'Fitup Start':      0.75,
    'Fitup Complete':   0.5,
    'Weld Start':       0.4,
    'Weld Complete':    0.0,
    'Hold':             0.0,
    'Welded QC':        0.0,
    'Paint Start':      0.0,
    'Paint Complete':   0.0,
    'Store at MHMW':    0.0,
    'Ship Planning':    0.0,
    'Ship Complete':    0.0,
    'Install Start':    0.0,
    'Install Complete': 0.0,
    'Complete':         0.0,
};

export function getFabModifier(stage) {
    return stage in FAB_MODIFIER ? FAB_MODIFIER[stage] : 1.0;
}

export function computeTotalFabHrs(jobs) {
    return jobs.reduce(
        (sum, job) => sum + (job['Fab Hrs'] || 0) * getFabModifier(job['Stage'] || ''),
        0,
    );
}
