/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Renders a compact card preview for a board item in the Kanban list, with priority-colored left border and status badge.
 * exports:
 *   BoardItemCard: Clickable card component showing title, status, category, author, and activity count
 * imports_from: []
 * imported_by: []
 * invariants:
 *   - Priority border color falls back to "normal" if the priority key is unrecognized
 * updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
 */
const PRIORITY_BORDER = {
    urgent: 'border-l-red-500',
    high: 'border-l-orange-500',
    normal: 'border-l-accent-500',
    low: 'border-l-gray-400',
};

const STATUS_BADGE = {
    open: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
    in_progress: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300',
    deployed: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300',
    closed: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400',
};

const STATUS_LABELS = {
    open: 'Open',
    in_progress: 'In Progress',
    deployed: 'Deployed',
    closed: 'Closed',
};

function timeAgo(isoString) {
    if (!isoString) return '';
    const ts = isoString.endsWith('Z') ? isoString : isoString + 'Z';
    const diff = Date.now() - new Date(ts).getTime();
    if (diff < 0) return 'just now';
    const mins = Math.floor(diff / 60000);
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    const days = Math.floor(hrs / 24);
    return `${days}d ago`;
}

export default function BoardItemCard({ item, isSelected, onClick }) {
    return (
        <button
            type="button"
            onClick={onClick}
            className={`w-full text-left border-l-4 ${PRIORITY_BORDER[item.priority] || PRIORITY_BORDER.normal} rounded-lg shadow-sm transition-all cursor-pointer
                ${isSelected
                    ? 'bg-accent-50 dark:bg-slate-700 ring-2 ring-accent-500'
                    : 'bg-white dark:bg-slate-800 hover:bg-gray-50 dark:hover:bg-slate-750 hover:shadow-md'
                }`}
        >
            <div className="px-4 py-3">
                <div className="flex items-start justify-between gap-2">
                    <h3 className="text-sm font-semibold text-gray-900 dark:text-slate-100 leading-tight">
                        {item.title}
                    </h3>
                    <span className={`shrink-0 px-2 py-0.5 text-xs font-medium rounded-full ${STATUS_BADGE[item.status] || STATUS_BADGE.open}`}>
                        {STATUS_LABELS[item.status] || item.status}
                    </span>
                </div>
                <div className="mt-1.5 flex items-center gap-2 text-xs text-gray-500 dark:text-slate-400">
                    <span className="px-1.5 py-0.5 rounded bg-gray-100 dark:bg-slate-700 font-medium">
                        {item.category}
                    </span>
                    <span>{item.author_name}</span>
                    <span className="text-gray-400 dark:text-slate-500">{timeAgo(item.updated_at)}</span>
                    {item.activity_count > 0 && (
                        <span className="ml-auto flex items-center gap-0.5">
                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                            </svg>
                            {item.activity_count}
                        </span>
                    )}
                </div>
            </div>
        </button>
    );
}
