/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Renders the Job Log's active filters as removable chips (one per filter) plus a clear-all,
 *   so every active filter is visible and individually dismissible.
 * exports:
 *   ActiveFilterChips: default — props for each filter slice + removal callbacks (see below)
 * imports_from: [react, ../constants/columnHeaders]
 * imported_by: [../pages/JobLog.jsx]
 * invariants:
 *   - Returns null when no filter is active (caller need not guard).
 *   - One chip per project, one chip per column filter, one for subset/review, one for sort, one for search.
 */
import { HEADER_OVERRIDES } from '../constants/columnHeaders';

const SUBSET_LABELS = {
    job_order: 'Job Order',
    ready_to_ship: 'Ready to Ship',
    paint: 'Paint',
    paint_fab: 'Paint+Fab',
    fab: 'Fab',
};

function Chip({ label, onRemove, title }) {
    return (
        <span
            className="inline-flex items-center gap-1 pl-2 pr-1 py-0.5 bg-blue-100 dark:bg-blue-900/50 text-blue-800 dark:text-blue-200 rounded-full text-xs font-medium max-w-[260px]"
            title={title}
        >
            <span className="truncate">{label}</span>
            <button
                type="button"
                onClick={onRemove}
                className="flex-shrink-0 w-4 h-4 inline-flex items-center justify-center rounded-full hover:bg-blue-200 dark:hover:bg-blue-800 leading-none"
                aria-label={`Remove ${label}`}
            >
                ×
            </button>
        </span>
    );
}

export default function ActiveFilterChips({
    search,
    selectedSubset,
    reviewMode,
    selectedProjectNames = [],
    columnFilters = {},
    columnSort,
    onClearSearch,
    onClearSubset,
    onClearReview,
    onRemoveProject,
    onClearColumnFilter,
    onClearSort,
    onClearAll,
}) {
    const hasSearch = !!(search && search.trim());
    const columnFilterKeys = Object.keys(columnFilters).filter((k) => (columnFilters[k] || []).length > 0);
    const hasSort = !!(columnSort && columnSort.column && columnSort.direction);

    const anyActive =
        hasSearch ||
        !!selectedSubset ||
        reviewMode ||
        selectedProjectNames.length > 0 ||
        columnFilterKeys.length > 0 ||
        hasSort;

    if (!anyActive) return null;

    const colLabel = (col) => HEADER_OVERRIDES[col] ?? col;

    return (
        <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-xs font-semibold text-gray-500 dark:text-slate-400 whitespace-nowrap">Active filters:</span>

            {hasSearch && (
                <Chip label={`Search: "${search.trim()}"`} title={`Search: ${search.trim()}`} onRemove={onClearSearch} />
            )}

            {selectedSubset && (
                <Chip label={SUBSET_LABELS[selectedSubset] ?? selectedSubset} onRemove={onClearSubset} />
            )}

            {reviewMode && <Chip label="Review" onRemove={onClearReview} />}

            {selectedProjectNames.map((name) => (
                <Chip key={`proj-${name}`} label={`Project: ${name}`} title={`Project: ${name}`} onRemove={() => onRemoveProject(name)} />
            ))}

            {columnFilterKeys.map((col) => {
                const vals = columnFilters[col];
                const shown = vals.slice(0, 3).join(', ');
                const more = vals.length > 3 ? ` +${vals.length - 3}` : '';
                return (
                    <Chip
                        key={`col-${col}`}
                        label={`${colLabel(col)}: ${shown}${more}`}
                        title={`${colLabel(col)}: ${vals.join(', ')}`}
                        onRemove={() => onClearColumnFilter(col)}
                    />
                );
            })}

            {hasSort && (
                <Chip
                    label={`Sorted: ${colLabel(columnSort.column)} ${columnSort.direction === 'asc' ? '↑' : '↓'}`}
                    onRemove={onClearSort}
                />
            )}

            <button
                type="button"
                onClick={onClearAll}
                className="text-xs text-blue-600 dark:text-blue-400 underline hover:no-underline whitespace-nowrap ml-1"
                title="Remove every active filter and sort."
            >
                Clear all
            </button>
        </div>
    );
}
