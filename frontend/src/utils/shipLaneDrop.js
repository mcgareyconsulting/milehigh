/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Rules for dropping a release onto one of the Timeline's two shipping lanes. A shipping
 *   drop writes the STAGE ONLY, so these are the guards and the wording that make an otherwise
 *   invisible write legible: can it happen, and what does the user get told before they let go.
 *   Pure — no React, no DOM, no fetching — so the rules can be tested without layout.
 * exports:
 *   SHIP_COMPLETE_STAGE: The DB Stage value the Shipping Completed lane writes
 *   hasHardInstall: Does this release carry a hard (non-formula) Start install date
 *   shipLaneDropOutcome: Classify a drop — 'write' | 'noop' | 'blocked' — with its user-facing wording
 *   shipLabelFor: The hover label naming what the drop will do
 * imports_from: []
 * imported_by: [../components/GanttChart.jsx]
 * invariants:
 *   - The Shipping Completed lane positions a card on its HARD Start install date, and the backend's
 *     N5 shipping-stage discipline blanks estimated dates on the way in. A release without a hard
 *     date would land nowhere and vanish off the board, so that drop is BLOCKED, not performed.
 *   - Dropping onto the lane a release is already in is a no-op, never a redundant write.
 *   - Shipping Planning has no such guard: it is reachable from any stage, and its card falls back
 *     to an estimated ship date.
 *   - These rules never mention a DATE the drop would write, because a shipping drop writes none.
 */

export const SHIP_COMPLETE_STAGE = 'Ship Complete';

/** A hard date is an explicit one the scheduler will not overwrite; a formula date is a projection. */
export const hasHardInstall = (row) =>
    row?.start_install_formulaTF === false && !!row?.['Start install'];

/**
 * What would happen if this release were dropped on the lane that writes `stage`.
 *
 * Returns { kind, label, reason } where kind is:
 *   'noop'    — already in that stage; drop does nothing
 *   'blocked' — the drop is refused; `reason` completes a sentence, `label` fits a hover chip
 *   'write'   — the stage change goes through
 *
 * `label` and `reason` are separate on purpose: a chip wants a terse imperative, a toast wants a
 * clause. Lower-casing the chip to reuse it would mangle the field name "Start install".
 */
export const shipLaneDropOutcome = (row, stage) => {
    if ((row?.['Stage'] ?? '') === stage) {
        return { kind: 'noop', label: `Already ${stage}` };
    }
    if (stage === SHIP_COMPLETE_STAGE && !hasHardInstall(row)) {
        return {
            kind: 'blocked',
            label: 'Needs a hard Start install',
            reason: 'it has no hard Start install date to sit on',
        };
    }
    return { kind: 'write', label: `Set stage → ${stage}` };
};

/** The hover label — said BEFORE the user lets go, since a stage change leaves no mark at the drop point. */
export const shipLabelFor = (row, stage) => shipLaneDropOutcome(row, stage).label;
