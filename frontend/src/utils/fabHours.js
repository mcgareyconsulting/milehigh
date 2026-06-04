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
 *   - This table is the source of truth for the FRONTEND. The backend mirrors
 *     it as a SQL CASE in app/brain/job_log/routes.py (/brain/fab-hours-total).
 *     Keep both in sync when stage modifiers change.
 */

export const FAB_MODIFIER = {
    'Released':         1.0,
    'Cut Start':        0.9,
    'Fitup Complete':   0.5,
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
