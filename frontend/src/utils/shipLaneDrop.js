/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Rules for dropping a release onto one of the Timeline's two shipping lanes. A shipping
 *   drop writes the STAGE ONLY, so these are the guards and the wording that make an otherwise
 *   invisible write legible: can it happen, and what does the user get told before they let go.
 *   Pure — no React, no DOM, no fetching — so the rules can be tested without layout.
 * exports:
 *   SHIP_COMPLETE_STAGE: The DB Stage value the Shipping Completed lane writes
 *   SHIP_PLANNING_STAGE: The DB Stage value the Shipping Planning lane writes
 *   hasHardInstall: Does this release carry a hard (non-formula) Start install date
 *   shipLaneDropOutcome: Classify a drop — 'write' | 'noop' | 'blocked' — with its user-facing wording
 *   shipLabelFor: The hover label naming what the drop will do
 * imports_from: []
 * imported_by: [../components/GanttChart.jsx, ./unassignedLane.js, ./readyToShipColumn.js]
 * invariants:
 *   - The Shipping Completed lane positions a card on its HARD Start install date, and the backend's
 *     N5 shipping-stage discipline blanks estimated dates on the way in. A release without a hard
 *     date would land nowhere and vanish off the board, so that drop is BLOCKED, not performed.
 *   - Dropping onto the lane a release is already in is a no-op, never a redundant write.
 *   - Shipping Planning has no such guard: it is reachable from any stage, and its card falls back
 *     to an estimated ship date.
 *   - A Shipping Planning drop writes the STAGE ONLY *when the release already has a hard Start
 *     install date* — its X is derived from that date, so honouring the drop column would move a
 *     date nobody aimed at. When the release has NO hard date the drop writes BOTH: the column's
 *     date and the stage. That is not an exception to the rule above, it is the same rule read the
 *     other way — there is no date to protect, and a Ship Planning card with no date renders
 *     nowhere at all, so the drop has to supply one or it silently loses the card. This is the
 *     Ready-to-Ship column's one exit (see ./readyToShipColumn), and `writesDate` is what says so.
 *   - Shipping Completed never writes a date: `blocked` already refuses the only case where it
 *     would have to, and inventing an install date is a much larger claim than planning a ship.
 */

export const SHIP_COMPLETE_STAGE = 'Ship Complete';
export const SHIP_PLANNING_STAGE = 'Ship Planning';

/** A hard date is an explicit one the scheduler will not overwrite; a formula date is a projection. */
export const hasHardInstall = (row) =>
    row?.start_install_formulaTF === false && !!row?.['Start install'];

/**
 * What would happen if this release were dropped on the lane that writes `stage`.
 *
 * Returns { kind, label, reason, writesDate } where kind is:
 *   'noop'    — already in that stage; drop does nothing
 *   'blocked' — the drop is refused; `reason` completes a sentence, `label` fits a hover chip
 *   'write'   — the stage change goes through
 *
 * `writesDate` is true only on a Shipping Planning drop onto a release with no hard Start install:
 * there the drop column IS the choice being made, and the caller stamps it as a hard date.
 *
 * `label` and `reason` are separate on purpose: a chip wants a terse imperative, a toast wants a
 * clause. Lower-casing the chip to reuse it would mangle the field name "Start install".
 */
export const shipLaneDropOutcome = (row, stage) => {
    if ((row?.['Stage'] ?? '') === stage) {
        return { kind: 'noop', label: `Already ${stage}`, writesDate: false };
    }
    if (stage === SHIP_COMPLETE_STAGE && !hasHardInstall(row)) {
        return {
            kind: 'blocked',
            label: 'Needs a hard Start install',
            reason: 'it has no hard Start install date to sit on',
            writesDate: false,
        };
    }
    const writesDate = stage === SHIP_PLANNING_STAGE && !hasHardInstall(row);
    return { kind: 'write', label: `Set stage → ${stage}`, writesDate };
};

/**
 * The hover label — said BEFORE the user lets go, since a stage change leaves no mark at the drop
 * point. When the drop also stamps a date, the label has to name it: that is the half of the write
 * the user is actually aiming with, and a column is far too small a target to leave unconfirmed.
 *
 * @param {object} row        the release being dragged
 * @param {string} stage      the stage the lane writes
 * @param {string} [dateText] the drop column's date, already formatted for display
 */
export const shipLabelFor = (row, stage, dateText) => {
    const outcome = shipLaneDropOutcome(row, stage);
    if (outcome.writesDate && dateText) {
        return `${stage} · ${dateText}`;
    }
    return outcome.label;
};
