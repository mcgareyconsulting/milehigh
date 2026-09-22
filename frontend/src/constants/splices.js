/**
 * Splice-group rules the UI flags (roadmap T9; training handout 2026-09-21, "Rules").
 *
 * "Many splices: lots of splices on one job = problem flag (cleanup / scope creep).
 * Exception: clarifying hold-downs by building." The count is per original release,
 * which is where splices hang. The threshold is a judgment call, not a rule the
 * server enforces: nothing is blocked, the group is just flagged for a look.
 */

export const MANY_SPLICES_THRESHOLD = 4;

export function hasManySplices(count) {
    return Number(count) >= MANY_SPLICES_THRESHOLD;
}
