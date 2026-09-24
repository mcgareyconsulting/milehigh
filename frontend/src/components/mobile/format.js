/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Tiny formatting helpers shared by the phone shells and pages (sub portal + employee
 *          mobile) so the same date reads the same way on every card, and the month-chip list is
 *          built once.
 * exports:
 *   initialsOf(name) — "McGarey Construction" -> "MC"
 *   fmtDay(iso) — "Wed, Sep 3" (date-only or datetime input); null/invalid -> null
 *   fmtShort(iso) — "Sep 3"
 *   timeAgo(iso) — "4m ago" / "2d ago" / "Sep 3"
 *   todayDenver() — today's YYYY-MM-DD in the company timezone
 *   addDays(isoDate, n) — YYYY-MM-DD arithmetic on a date-only string
 *   monthOptions(today?) — [{ key: 'YYYY-MM', label: 'Sep' | "Jan '27" }] from last month to 4 out
 * imports_from: []
 * imported_by: [SubcontractorShell, StaffMobileShell, TodosMobile, SubReleaseDetails,
 *               SubReleaseAttachments, MonthChips]
 */
export const COMPANY_TZ = 'America/Denver';

export function initialsOf(name) {
    const words = String(name || '').trim().split(/\s+/).filter(Boolean);
    if (!words.length) return '?';
    return (words.length === 1 ? words[0].slice(0, 2) : words[0][0] + words[1][0]).toUpperCase();
}

const parse = (iso) => {
    if (!iso) return null;
    const d = new Date(String(iso).length <= 10 ? `${iso}T00:00:00` : iso);
    return isNaN(d) ? null : d;
};

export function fmtDay(iso) {
    const d = parse(iso);
    return d ? d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' }) : null;
}

export function fmtShort(iso) {
    const d = parse(iso);
    return d ? d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : null;
}

export function timeAgo(dateStr) {
    const seconds = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
    if (!Number.isFinite(seconds)) return '';
    if (seconds < 60) return 'just now';
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    if (days < 30) return `${days}d ago`;
    return fmtShort(dateStr) || '';
}

export const todayDenver = () => new Intl.DateTimeFormat('en-CA', { timeZone: COMPANY_TZ }).format(new Date());

export function addDays(iso, n) {
    const d = new Date(`${iso}T00:00:00`);
    d.setDate(d.getDate() + n);
    return new Intl.DateTimeFormat('en-CA').format(d);
}

export function monthOptions(today = new Date()) {
    const out = [];
    for (let i = -1; i <= 4; i += 1) {
        const d = new Date(today.getFullYear(), today.getMonth() + i, 1);
        const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
        const label = d.toLocaleDateString('en-US', d.getFullYear() === today.getFullYear()
            ? { month: 'short' } : { month: 'short', year: '2-digit' });
        out.push({ key, label, isCurrent: i === 0 });
    }
    return out;
}
