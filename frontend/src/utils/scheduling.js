/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Client-side mirror of the backend install-schedule math
 *   (app/brain/job_log/scheduling/calculator.py :: calculate_install_complete_date), so the
 *   read-only "cockpit" preview in ReleaseCockpitModal recomputes the exact dates the server
 *   would, without any network round-trip. Pure functions over YYYY-MM-DD strings.
 * exports:
 *   installDays: work days an install spans for (install_hrs, num_guys)
 *   installCompleteDate: comp_eta = start + (installDays - 1) business days
 *   shipEstimate: estimated ship = start - 1 business day
 *   businessDaysBetween: signed business-day distance between two dates (for deltas)
 * imports_from: [./formatters]
 * imported_by: [components/ReleaseCockpitModal.jsx, utils/scheduling.test.js]
 * invariants:
 *   - Must stay in lockstep with the backend SchedulingConfig: HOURS_PER_INSTALLER_DAY = 8,
 *     DEFAULT_NUM_GUYS = 2. Change both together.
 *   - install_hrs <= 0 (or missing) means "no duration": comp_eta == start (a same-day install).
 *   - Weekends (Sat/Sun) are skipped; all offsets are business days.
 */
import { toYmd, addBusinessDays, subtractBusinessDays } from './formatters';

// Keep in sync with backend SchedulingConfig.
export const HOURS_PER_INSTALLER_DAY = 8;
export const DEFAULT_NUM_GUYS = 2;

/**
 * Work days an install spans. Daily capacity = num_guys * 8 hrs; days = ceil(hrs / capacity),
 * floored at 1 for any positive hours. Returns 0 when there are no positive install hours
 * (a same-day / no-duration install), matching the backend's `install_hours == 0 -> start`.
 */
export function installDays(installHrs, numGuys) {
    const hrs = Number(installHrs);
    if (!Number.isFinite(hrs) || hrs <= 0) return 0;
    let guys = Number(numGuys);
    if (!Number.isFinite(guys) || guys <= 0) guys = DEFAULT_NUM_GUYS;
    const capacity = guys * HOURS_PER_INSTALLER_DAY;
    return Math.max(1, Math.ceil(hrs / capacity));
}

/**
 * comp_eta for (start, install_hrs, num_guys): the LAST working day of the install
 * (inclusive of the start day). Returns '' if there is no start date.
 */
export function installCompleteDate(startYmd, installHrs, numGuys) {
    const start = toYmd(startYmd);
    if (!start) return '';
    const days = installDays(installHrs, numGuys);
    if (days <= 0) return start;           // no positive hours -> completes the day it starts
    return addBusinessDays(start, days - 1);
}

/** Estimated ship date = one business day before a hard start install. '' if no start. */
export function shipEstimate(startYmd) {
    const start = toYmd(startYmd);
    if (!start) return '';
    return subtractBusinessDays(start, 1);
}

/**
 * Signed business-day distance from `aYmd` to `bYmd` (positive if b is later). Weekends are
 * not counted. Used for the cockpit's "+N days later / -N sooner" deltas.
 */
export function businessDaysBetween(aYmd, bYmd) {
    const a = toYmd(aYmd);
    const b = toYmd(bYmd);
    if (!a || !b || a === b) return 0;
    const [ay, am, ad] = a.split('-').map(Number);
    const [by, bm, bd] = b.split('-').map(Number);
    const start = new Date(ay, am - 1, ad);
    const end = new Date(by, bm - 1, bd);
    const step = end > start ? 1 : -1;
    let n = 0;
    const cur = new Date(start);
    while (cur.getTime() !== end.getTime()) {
        cur.setDate(cur.getDate() + step);
        const dow = cur.getDay();
        if (dow !== 0 && dow !== 6) n += step;
    }
    return n;
}
