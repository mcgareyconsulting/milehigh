/**
 * @milehigh-header
 * schema_version: 1
 * purpose: One reading of a release's install hours across every view (T9 splices).
 *   A release with splices under it keeps the WHOLE pool in install_hrs — the hours a
 *   splice drew are never subtracted from it, or the pool would shrink each time it was
 *   drawn on. So 150 hrs with 50 spliced to 340.1 must READ as 100 on the original
 *   everywhere it is shown, while the stored total stays 150 for editing and pool math.
 * exports:
 *   installHrsOwn: hours a release still installs itself (remaining, else its total)
 *   installHrsTotal: the release's whole pool (the stored install_hrs)
 *   splicedHrs: hours live splices drew off it (0 when none / not a splice parent)
 *   hasSplicedHours: true when splices drew hours off this release
 *   installHrsNote: one-line "150 total · 50 spliced to splices" for a tooltip, else null
 * imports_from: []
 * imported_by: [components/JobsTableRow.jsx, components/JobDetailsBody.jsx,
 *   components/SplicesPane.jsx, pages/Subs.jsx, utils/subsInvoiceExport.js]
 * invariants:
 *   - Reads both payload shapes: Job Log rows key hours as 'Install HRS', Subs rows as
 *     install_hrs. spliced_install_hrs / remaining_install_hrs travel on both, and are
 *     null unless live splices drew hours off the row (app/brain/.../splice/command.py).
 *   - Never computes the split client-side — the server owns it; this only picks.
 *   - Anything that WRITES install hours uses installHrsTotal: the edit is to the pool.
 */

const num = (v) => {
    if (v == null || v === '') return null;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
};

/** The release's whole install-hour pool, as stored. Null when it has none. */
export function installHrsTotal(row) {
    if (!row) return null;
    const display = num(row['Install HRS']);
    return display == null ? num(row.install_hrs) : display;
}

/** Hours live splices drew off this release. 0 when nothing was spliced off it. */
export function splicedHrs(row) {
    return row ? (num(row.spliced_install_hrs) ?? 0) : 0;
}

export function hasSplicedHours(row) {
    return splicedHrs(row) > 0;
}

/**
 * Hours this release still installs ITSELF — the number every view shows.
 * Its pool minus what splices drew; its plain total when nothing was spliced off it.
 */
export function installHrsOwn(row) {
    if (!row) return null;
    const remaining = num(row.remaining_install_hrs);
    return remaining == null ? installHrsTotal(row) : remaining;
}

/** Tooltip line explaining a netted number, or null when there is nothing to explain. */
export function installHrsNote(row) {
    const spliced = splicedHrs(row);
    if (spliced <= 0) return null;
    const total = installHrsTotal(row);
    const own = installHrsOwn(row);
    const totalPart = total == null ? '' : `${total} total install hrs · `;
    return `${totalPart}${spliced} spliced off to splices · ${own ?? '—'} left on this release`;
}
