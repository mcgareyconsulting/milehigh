/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Membership rule for the Timeline's pinned Unassigned staging column — the set of
 *   releases that are finished in the shop but have nobody scheduled to install them. Pure
 *   selector over the shared releases dataset; no fetching, no writes.
 * exports:
 *   READY_TO_SHIP_STAGES: The three shop states that make a release stageable (Bill's intake, verbatim)
 *   isUnassigned: Predicate — no installer AND in a ready-to-ship stage
 *   selectUnassigned: Filter + deterministic sort of the whole dataset into staging-column order
 * imports_from: []
 * imported_by: [../components/GanttChart.jsx, ../hooks/useJobsFilters.js]
 * invariants:
 *   - Membership is "no installer assigned AND (ready to ship OR stored at Mile High OR past paint
 *     complete)". Deliberately NOT "any release with no installer": that pulls in every drafting and
 *     fabrication row and the column stops being a work surface.
 *   - READY_TO_SHIP_STAGES is the SAME set the Job Log's "Ready to Ship" quick filter uses. Both
 *     import it from here so the two surfaces can never drift apart.
 *   - Sort is ASAP first, then job # asc, then release # asc — matching the timeline's inCellSort so
 *     a card keeps its relative neighbours when it moves from the column into a lane.
 */

// The three shop states Bill named as the staging intake: "see what's ready to ship, see what's
// stored at Mile High, grab anything past paint complete." Canonical DB Stage values — see
// app/api/helpers.py STAGE_PROGRESSION_RANK (11, 12, 13).
export const READY_TO_SHIP_STAGES = ['Ship Planning', 'Store at MHMW', 'Paint Complete'];

const READY_TO_SHIP_SET = new Set(READY_TO_SHIP_STAGES);

const stageOf = (job) => String(job?.['Stage'] ?? '').trim();
const installerOf = (job) => String(job?.installer ?? '').trim();

/**
 * Is this release waiting in the staging column?
 *
 * True when nobody is assigned to install it AND the shop is done enough with it that it can be
 * scheduled. A release that already has an installer lives in that installer's lane instead, so it
 * must never appear in both places.
 */
export const isUnassigned = (job) =>
    !installerOf(job) && READY_TO_SHIP_SET.has(stageOf(job));

/**
 * Staging-column contents, in display order.
 *
 * ASAP rush jobs float to the top so they get picked up first, then job # / release # ascending so
 * the order is stable across the 30s poll and never reshuffles under a drag.
 */
export const selectUnassigned = (jobs) =>
    (jobs || []).filter(isUnassigned).sort((a, b) => {
        const aAsap = a['start_install_asap'] === true ? 0 : 1;
        const bAsap = b['start_install_asap'] === true ? 0 : 1;
        if (aAsap !== bAsap) return aAsap - bAsap;
        const jobDiff = (Number(a['Job #']) || 0) - (Number(b['Job #']) || 0);
        if (jobDiff !== 0) return jobDiff;
        return String(a['Release #'] ?? '').localeCompare(String(b['Release #'] ?? ''), undefined, { numeric: true });
    });
