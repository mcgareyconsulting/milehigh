/**
 * @milehigh-header
 * schema_version: 1
 * purpose: One place to decide how a release's install date should be colored — ASAP red, overdue amber, future green, or neutral. Mirrors the backend's _classify_date (app/brain/install_schedule/service.py) and the COLOR_DUMP_STAGES rule (app/brain/job_log/features/start_install/neutralize_install_date_cascade.py).
 * exports:
 *   COLOR_DUMP_STAGES: Stages at which a hard install date's color is dropped
 *   isInstallStartOrLater: True when a stage is in the dump zone
 *   classifyInstallDate: {isAsap, isNoColor, isHardDate, isHardDatePast} for one release
 *   localTodayYmd: Today as YYYY-MM-DD in LOCAL time
 * imports_from: []
 * imported_by: [components/JobsTableRow.jsx, components/StartInstallEditor.jsx]
 * invariants:
 *   - Precedence is ASAP > neutral > hard date; the first match wins, matching the backend
 *   - Dates compare as local YYYY-MM-DD strings — toISOString would shift the day in UTC-N
 *   - The stage check also covers the optimistic window: right after a stage change the row
 *     has the new stage but not yet the refetched start_install_no_color
 */

// BUG-11: a hard date's color drops when install STARTS, not when it ships. Bill reversed
// the earlier rule — a yellow overdue date is a scored EOS metric and must stay visible
// through the ship stages, where the install is still ahead of us.
//
// Keep in step with COLOR_DUMP_STAGES in
// app/brain/job_log/features/start_install/neutralize_install_date_cascade.py.
export const COLOR_DUMP_STAGES = ['Install Start', 'Install Complete', 'Complete'];

export const isInstallStartOrLater = (stage) => COLOR_DUMP_STAGES.includes(stage);

// Local, not UTC: toISOString() rolls the date back a day for anyone west of Greenwich,
// which would show a date as overdue a day early.
export function localTodayYmd(now = new Date()) {
    const m = String(now.getMonth() + 1).padStart(2, '0');
    const d = String(now.getDate()).padStart(2, '0');
    return `${now.getFullYear()}-${m}-${d}`;
}

/**
 * Classify one release's install date. Callers map the result onto their own classes —
 * the Job Log table and the modal tile style these differently.
 *
 * @param {object}  args
 * @param {string}  args.stage        Current stage (use the optimistic local value if any)
 * @param {boolean} args.asap         start_install_asap
 * @param {boolean} args.noColor      start_install_no_color
 * @param {boolean} args.formulaTF    start_install_formulaTF (false === hard date)
 * @param {*}       args.installDate  start_install ('YYYY-MM-DD' or ISO)
 * @param {string} [args.today]       Override for tests
 */
export function classifyInstallDate({ stage, asap, noColor, formulaTF, installDate, today }) {
    const dumped = isInstallStartOrLater(stage);
    // Past Install Start the color is already dumped, so ASAP can no longer paint it red —
    // and the server refuses to set ASAP there at all.
    const isAsap = !dumped && asap === true;
    const isNoColor = dumped || noColor === true;
    const isHardDate = !isAsap && !isNoColor && formulaTF === false && !!installDate;
    const day = String(installDate ?? '').split('T')[0];
    const isHardDatePast = isHardDate && day < (today ?? localTodayYmd());
    return { isAsap, isNoColor, isHardDate, isHardDatePast };
}
