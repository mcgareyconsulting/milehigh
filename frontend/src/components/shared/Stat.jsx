/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Small labeled stat tile (uppercase label + bold value) shared across report/metrics dashboards.
 * exports:
 *   Stat: Tile component. Props: label, value, tone ('default'|'red'|'amber'|'orange'|'slate'|'green'), sub (optional secondary line).
 * imports_from: []
 * imported_by: [pages/RentalReports.jsx, pages/Metrics.jsx]
 * invariants:
 *   - Light + dark themed; extracted from RentalReports so both surfaces stay visually identical.
 */
const TONES = {
    default: 'text-gray-900 dark:text-slate-100',
    red: 'text-red-600 dark:text-red-400',
    amber: 'text-amber-600 dark:text-amber-400',
    orange: 'text-orange-600 dark:text-orange-400',
    slate: 'text-gray-500 dark:text-slate-400',
    green: 'text-green-600 dark:text-green-400',
};

export default function Stat({ label, value, tone = 'default', sub = null }) {
    return (
        <div className="rounded-lg border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2">
            <div className="text-[10px] uppercase tracking-wide text-gray-400 dark:text-slate-500">{label}</div>
            <div className={`text-lg font-bold leading-tight ${TONES[tone]}`}>{value}</div>
            {sub != null && <div className="text-[11px] text-gray-400 dark:text-slate-500 mt-0.5">{sub}</div>}
        </div>
    );
}
