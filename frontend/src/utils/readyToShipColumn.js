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
 *   isUpstreamAsap: Predicate — an ASAP still in Paint or Fabrication (visibility only)
 *   READY_TO_SHIP_SECTIONS: Section keys + labels, in display order
 *   selectReadyToShip: Filter + deterministic sort of the whole dataset into column order
 * imports_from: [./shipLaneDrop]
 * imported_by: [../components/GanttChart.jsx, ../hooks/useJobsFilters.js]
 * invariants:
 *   - Membership is "NO hard Start install date AND NOT already Ship Planning". The column exists to
 *     answer one question — what still needs a day — so the moment a release gets a hard date and
 *     rolls into Ship Planning it leaves, and it leaves in the same gesture that gave it the date.
 *   - A projected (formula) date does NOT count as having a date. The Brain guesses one for almost
 *     every fab row; treating a guess as a commitment would empty the column of exactly the work it
 *     is meant to surface. Hard-vs-projected is `hasHardInstall` (./shipLaneDrop), the same test the
 *     ship lanes and the Job Log's Start install cell use.
 *   - Two intakes:
 *       (a) the in-shop holds — Store at MHMW and Paint Complete with no hard Start install. These
 *          are the column's WORK: each needs a ship day, and is dragged to Shipping Planning for one.
 *       (b) ASAPs still in Paint or Fabrication, for VISIBILITY only — the shipping desk should see
 *          rush work coming before it lands. Setting ASAP always writes a hard date, so these are
 *          matched on stage + ASAP with NO date test (a date test would never let one in). They
 *          do not count as "needing a ship date" and the column renders them non-draggable: a drop
 *          on Shipping Planning would move a release that is still being built.
 *   - DISJOINT from the Unassigned tray by construction (see ./unassignedLane): the tray keeps the
 *     dated and the Ship Planning rows, this column keeps the undated ones. No card appears twice.
 *   - Sections, in order: Paint Complete, Store at MHMW, then the upstream ASAPs as a trailing block
 *     (a heads-up about what is coming never interleaves with painted steel on the floor). Each row
 *     is tagged `_rtsSection` so the column can draw a header where the section changes; upstream
 *     rows also carry `_asapOrigin` ('Fab' / 'Paint') for the card's "in Fab" / "in Paint" chip.
 *   - WITHIN a section, rows sort by Start install date (the projected one — by membership there is
 *     no hard date) ascending, undated last; ties break on job # / release # so the order is stable
 *     across the 30s poll and never reshuffles under a drag.
 */

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

// Display order of the column's sections. Keys are what `_rtsSection` carries.
export const READY_TO_SHIP_SECTIONS = [
    { key: 'paint', label: 'Paint Complete' },
    { key: 'store', label: 'Store at MHMW' },
    { key: 'upstream', label: 'ASAP · in Fab / Paint' },
];
const SECTION_RANK = { paint: 0, store: 1, upstream: 2 };

// Day part of Start install ('' when undated), so a date and a datetime compare as days.
const dayOf = (job) => String(job?.['Start install'] ?? '').split('T')[0];

/**
 * Is this release one of the column's in-shop holds still waiting on a ship day?
 *
 * Note there is NO installer test here, unlike the Unassigned tray. This column is about the date,
 * not the crew: a release someone has already promised to a crew but never dated is exactly the one
 * that falls through the cracks, and it still needs a day.
 */
export const isReadyToShip = (job) =>
    COLUMN_SET.has(stageOf(job)) && !hasHardInstall(job);

/** An ASAP still in the Paint department or the FABRICATION band — shown for visibility only. */
export const isUpstreamAsap = (job) =>
    job?.['start_install_asap'] === true
    && (PAINT_SET.has(stageOf(job)) || stageGroupOf(job) === 'FABRICATION');

const sectionOf = (job) => {
    if (isUpstreamAsap(job)) return 'upstream';
    return stageOf(job) === 'Paint Complete' ? 'paint' : 'store';
};

/**
 * Ready-to-Ship column contents, in display order.
 *
 * Rows are shallow copies of the shared dataset's rows plus render-only tags: `_rtsSection` (which
 * section header the row sits under) and, on an upstream ASAP, `_asapOrigin` ('Fab' / 'Paint').
 * Nothing here mutates the source row.
 */
export const selectReadyToShip = (jobs) =>
    (jobs || [])
        .filter((job) => isReadyToShip(job) || isUpstreamAsap(job))
        .map((job) => {
            const section = sectionOf(job);
            if (section !== 'upstream') return { ...job, _rtsSection: section };
            return { ...job, _rtsSection: section, _asapOrigin: PAINT_SET.has(stageOf(job)) ? 'Paint' : 'Fab' };
        })
        .sort((a, b) => {
            const sec = SECTION_RANK[a._rtsSection] - SECTION_RANK[b._rtsSection];
            if (sec !== 0) return sec;

            // Soonest wanted first; a release with no date at all sinks to the bottom of its section.
            const aDay = dayOf(a);
            const bDay = dayOf(b);
            if (aDay !== bDay) {
                if (!aDay) return 1;
                if (!bDay) return -1;
                return aDay < bDay ? -1 : 1;
            }

            const jobDiff = (Number(a['Job #']) || 0) - (Number(b['Job #']) || 0);
            if (jobDiff !== 0) return jobDiff;
            return String(a['Release #'] ?? '').localeCompare(
                String(b['Release #'] ?? ''), undefined, { numeric: true },
            );
        });
