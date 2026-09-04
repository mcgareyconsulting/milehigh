/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Membership rule for the Timeline's pinned Unassigned staging column — the set of
 *   releases that are finished in the shop but have nobody scheduled to install them. Pure
 *   selector over the shared releases dataset; no fetching, no writes.
 * exports:
 *   READY_TO_SHIP_STAGES: The three shop states that make a release stageable (Bill's intake, verbatim)
 *   isUnassigned: Predicate — no installer AND in a ready-to-ship stage
 *   trayDateKey: A release's Start install day string ('YYYY-MM-DD') or null — the tray's sort key
 *   selectUnassigned: Filter + deterministic sort of the whole dataset into staging-column order
 * imports_from: []
 * imported_by: [../components/GanttChart.jsx, ../hooks/useJobsFilters.js]
 * invariants:
 *   - Membership is "no installer assigned AND (ready to ship OR stored at Mile High OR past paint
 *     complete)". Deliberately NOT "any release with no installer": that pulls in every drafting and
 *     fabrication row and the column stops being a work surface.
 *   - READY_TO_SHIP_STAGES is the SAME set the Job Log's "Ready to Ship" quick filter uses. Both
 *     import it from here so the two surfaces can never drift apart.
 *   - Sort is ASAP first, then Start install date ascending, then job # / release # asc. The date
 *     orders the tray REGARDLESS of whether it is hard or projected (Bill, 2026-09-02): the column
 *     is a "what do I schedule next" queue, and a projected date is still the best answer the
 *     Brain has for when the work is due. Undated releases sink to the bottom — nothing to sort
 *     them against — rather than floating up as if they were overdue.
 *   - ASAP stays above the date order. It is a rush flag, not a date type, so "order by date
 *     regardless of hard/projected" does not demote it; its own anchor date would bury it behind
 *     anything due sooner.
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
 * The tray's sort key for a release's Start install date: 'YYYY-MM-DD', or null when there is
 * none. Dates are compared as day strings — the values arrive as 'YYYY-MM-DD' or a full ISO
 * stamp, and lopping the time off makes both compare correctly without a Date and its timezone.
 */
export const trayDateKey = (job) => {
    const raw = String(job?.['Start install'] ?? job?.start_install ?? '').trim();
    if (!raw) return null;
    const day = raw.split('T')[0];
    return /^\d{4}-\d{2}-\d{2}$/.test(day) ? day : null;
};

/**
 * Staging-column contents, in display order.
 *
 * ASAP rush jobs float to the top so they get picked up first. Everything else is ordered by
 * Start install date — hard or projected alike, since either one is a claim about when the work
 * is wanted — with undated releases last and job # / release # breaking ties so the order is
 * stable across the 30s poll and never reshuffles under a drag.
 */
export const selectUnassigned = (jobs) =>
    (jobs || []).filter(isUnassigned).sort((a, b) => {
        const aAsap = a['start_install_asap'] === true ? 0 : 1;
        const bAsap = b['start_install_asap'] === true ? 0 : 1;
        if (aAsap !== bAsap) return aAsap - bAsap;

        const aDate = trayDateKey(a);
        const bDate = trayDateKey(b);
        if (aDate !== bDate) {
            if (!aDate) return 1;   // undated sinks
            if (!bDate) return -1;
            return aDate < bDate ? -1 : 1;
        }

        const jobDiff = (Number(a['Job #']) || 0) - (Number(b['Job #']) || 0);
        if (jobDiff !== 0) return jobDiff;
        return String(a['Release #'] ?? '').localeCompare(String(b['Release #'] ?? ''), undefined, { numeric: true });
    });
