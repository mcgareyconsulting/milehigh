/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Parse naive-UTC server timestamps and display them in Mountain Time.
 * exports:
 *   parseServerTime: ISO string → Date; a naive string (no Z / offset) is treated as UTC
 *   formatMountain: Short "Sep 15, 2:30 PM" in America/Denver
 * imports_from: []
 * imported_by: [components/releaseIssues/ReleaseIssuesPane.jsx]
 * invariants:
 *   - Model to_dict timestamps (models._dt) are naive UTC isoformat. `new Date(bare)` reads them
 *     as LOCAL time, which shows UTC wall-clock — 6–7h late in Denver. Always go through here.
 *   - /brain/events is different: it is pre-formatted to a Mountain wall-clock string server-side.
 */

const HAS_ZONE = /(?:[zZ]|[+-]\d{2}:?\d{2})$/;

export function parseServerTime(iso) {
    if (!iso) return null;
    const s = String(iso);
    const d = new Date(HAS_ZONE.test(s) ? s : `${s}Z`);
    return isNaN(d) ? null : d;
}

export function formatMountain(iso) {
    const d = parseServerTime(iso);
    if (!d) return '';
    return d.toLocaleString('en-US', {
        timeZone: 'America/Denver', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
    });
}
