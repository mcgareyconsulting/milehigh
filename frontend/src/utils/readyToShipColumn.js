/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Membership rule for the Timeline's second pinned staging column — "Ready to Ship": the
 *   releases the shop is done (or nearly done) with that nobody has given a ship day to yet. Pure
 *   selector over the shared releases dataset; no fetching, no writes.
 * exports:
 *   READY_TO_SHIP_COLUMN_STAGES: The two in-shop holds this column owns (Ready to Ship minus Ship Planning)
 *   PAINT_STAGES: The Paint department's stages — shared with the Job Log's `paint` quick filter
 *   isReadyToShip: Predicate — in one of this column's stages, with no hard Start install date
 *   isUpstreamAsap: Predicate — an undated ASAP still moving through Paint or Fabrication
 *   selectReadyToShip: Filter + deterministic sort of the whole dataset into column order
 * imports_from: [./unassignedLane, ./shipLaneDrop]
 * imported_by: [../components/GanttChart.jsx, ../hooks/useJobsFilters.js]
 * invariants:
 *   - Membership is "NO hard Start install date AND NOT already Ship Planning". The column exists to
 *     answer one question — what still needs a day — so the moment a release gets a hard date and
 *     rolls into Ship Planning it leaves, and it leaves in the same gesture that gave it the date.
 *   - A projected (formula) date does NOT count as having a date. The Brain guesses one for almost
 *     every fab row; treating a guess as a commitment would empty the column of exactly the work it
 *     is meant to surface. Hard-vs-projected is `hasHardInstall` (./shipLaneDrop), the same test the
 *     ship lanes and the Job Log's Start install cell use.
 *   - Two intakes, mirroring the Job Log's Ready-to-Ship quick filter exactly:
 *       (a) the in-shop holds — Store at MHMW and Paint Complete;
 *       (b) OUT-OF-DEPARTMENT ASAPs — rush releases still in Paint or Fabrication. The Job Log
 *          surfaces those same rows at the bottom of its Ready-to-Ship filter (see
 *          useJobsFilters.propagatedAsapJobs) so a downstream foreman can see what is coming hot.
 *          They are tagged `_asapOrigin` here for the same reason: the card says where it still is.
 *   - DISJOINT from the Unassigned tray by construction (see ./unassignedLane): the tray keeps the
 *     dated and the Ship Planning rows, this column keeps the undated ones. No card appears twice.
 *   - Sort mirrors the Job Log's Ready-to-Ship filter exactly: the in-shop holds FIRST (ASAP at the
 *     top of them, then closest-to-done stage, then job # / release # asc), and the
 *     out-of-department ASAPs appended BELOW all of them — the Job Log renders those as a separate
 *     block at the bottom for the same reason [bill-2026-09-16#L1343]. An ASAP that is still in Fab
 *     is a warning about what is coming; an ASAP sitting painted on the floor is work to do now, and
 *     the two must not interleave. Ties break on job # / release # so the order is stable across the
 *     30s poll and never reshuffles under a drag.
 *   - Store at MHMW sorts above Paint Complete, matching the Job Log's current stage priority. The
 *     2026-09-16 ruling flips that pair (and renames Paint Complete to Paint QC) — when that lands,
 *     it lands in both places at once.
 */

import { SHIP_PLANNING_STAGE } from './unassignedLane';
import { hasHardInstall } from './shipLaneDrop';

// This column's own intake: the Ready-to-Ship set (./unassignedLane) minus Ship Planning, which is
// where a release goes when it LEAVES here. Canonical DB Stage values — app/api/helpers.py.
export const READY_TO_SHIP_COLUMN_STAGES = ['Store at MHMW', 'Paint Complete'];

// Stages that make up the Paint department (also the Job Log's `paint` quick-filter set).
export const PAINT_STAGES = ['Welded QC', 'Paint Start'];

const COLUMN_SET = new Set(READY_TO_SHIP_COLUMN_STAGES);
const PAINT_SET = new Set(PAINT_STAGES);

const stageOf = (job) => String(job?.['Stage'] ?? '').trim();
const stageGroupOf = (job) => String(job?.['Stage Group'] ?? '').trim();
const isAsap = (job) => job?.['start_install_asap'] === true;

// Closest-to-done first, so the top of the column is the work most nearly out the door.
// Anything unranked (an upstream ASAP) sinks below the in-shop holds.
const STAGE_RANK = { 'Store at MHMW': 0, 'Paint Complete': 1 };

/**
 * Is this release one of the column's in-shop holds still waiting on a ship day?
 *
 * Note there is NO installer test here, unlike the Unassigned tray. This column is about the date,
 * not the crew: a release someone has already promised to a crew but never dated is exactly the one
 * that falls through the cracks, and it still needs a day.
 */
export const isReadyToShip = (job) =>
    COLUMN_SET.has(stageOf(job)) && !hasHardInstall(job);

/**
 * Is this an ASAP still upstream — in Paint or Fabrication — with no day set?
 *
 * A rush release is the shipping desk's business well before it reaches Store/Paint Complete, which
 * is why the Job Log's Ready-to-Ship filter already lists these at its bottom. Same rows, same
 * reason, on the board.
 */
export const isUpstreamAsap = (job) =>
    isAsap(job)
    && !hasHardInstall(job)
    && stageOf(job) !== SHIP_PLANNING_STAGE
    && !COLUMN_SET.has(stageOf(job))
    && (PAINT_SET.has(stageOf(job)) || stageGroupOf(job) === 'FABRICATION');

/** Where an upstream ASAP is coming from, for the card's origin chip. '' for an in-shop hold. */
const originOf = (job) => {
    if (!isUpstreamAsap(job)) return '';
    return PAINT_SET.has(stageOf(job)) ? 'Paint' : 'Fab';
};

/**
 * Ready-to-Ship column contents, in display order.
 *
 * Rows are returned as-is from the shared dataset apart from `_asapOrigin`, a render-only tag the
 * card reads to say "still in Fab" / "still in Paint". Nothing here mutates the source row.
 */
export const selectReadyToShip = (jobs) =>
    (jobs || [])
        .filter((job) => isReadyToShip(job) || isUpstreamAsap(job))
        .map((job) => {
            const origin = originOf(job);
            return origin ? { ...job, _asapOrigin: origin } : job;
        })
        .sort((a, b) => {
            // Every in-shop hold ahead of every upstream ASAP: one is ready to leave the building,
            // the other is a heads-up about something still being built. A rush in Fab does not
            // outrank painted steel on the floor, so this key comes before the ASAP key.
            const aUp = a._asapOrigin ? 1 : 0;
            const bUp = b._asapOrigin ? 1 : 0;
            if (aUp !== bUp) return aUp - bUp;

            const aAsap = isAsap(a) ? 0 : 1;
            const bAsap = isAsap(b) ? 0 : 1;
            if (aAsap !== bAsap) return aAsap - bAsap;

            const aRank = STAGE_RANK[stageOf(a)] ?? 99;
            const bRank = STAGE_RANK[stageOf(b)] ?? 99;
            if (aRank !== bRank) return aRank - bRank;

            const jobDiff = (Number(a['Job #']) || 0) - (Number(b['Job #']) || 0);
            if (jobDiff !== 0) return jobDiff;
            return String(a['Release #'] ?? '').localeCompare(
                String(b['Release #'] ?? ''), undefined, { numeric: true },
            );
        });
