/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Formatting shared by the two Installation Schedule views (crew columns and the day-row
 *   vertical calendar). Both render the same card payload from the same endpoint family, so the
 *   date-kind colours live in one place — a release must not read as ASAP on one surface and Hard on
 *   the other. Split from the DatePill component because the fast-refresh lint rule requires a module
 *   to export either components or plain values, never both.
 * exports:
 *   DATE_KIND: date_kind -> {label, cls}, mirroring the Job Log StartInstallEditor convention.
 *   fmtDate: ISO -> "Thu, Sep 10"; fmtHours: number|null -> "8h" | "—".
 * imports_from: []
 * imported_by: [../components/installSchedule/DatePill.jsx,
 *   ../components/installSchedule/DaySchedule.jsx, ../pages/InstallSchedule.jsx]
 * invariants:
 *   - Estimated hours come only from the manual install_hrs field; null renders "—", never 0h. A
 *     fabricated zero reads as "no work", which is a different claim than "nobody entered it".
 */

export const DATE_KIND = {
    hard: { label: 'Hard', cls: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300 ring-1 ring-green-400/50' },
    asap: { label: 'ASAP', cls: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300 ring-1 ring-red-400/50' },
    projected: { label: 'Projected', cls: 'bg-surface-2 text-ink-2 ring-1 ring-hairline' },
    neutral: { label: 'Done', cls: 'bg-surface-2 text-ink-3' },
};

export const fmtDate = (iso) => {
    if (!iso) return '—';
    const d = new Date(`${iso}T00:00:00`);
    return isNaN(d) ? iso : d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
};

export const fmtHours = (h) => (h === null || h === undefined ? '—' : `${h}h`);
