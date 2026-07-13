/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Segmented Table/Timeline switcher for the two release views (Job Log table, Gantt timeline) — sits in the shared ReleasesLayout toolbar for instant switching over the shared ReleasesProvider dataset. (The PM Board view was removed 2026-07-12; /pm-board is now Timeline-only.)
 * exports:
 *   ReleasesViewSwitcher: Router-aware segmented control. Table → /job-log, Timeline → /pm-board.
 * imports_from: [react-router-dom]
 * imported_by: [frontend/src/pages/ReleasesLayout.jsx]
 * invariants:
 *   - Active segment derives from the current location (no local state), so deep links and back/forward stay correct.
 *   - Navigation only — never touches release data; switching views must not trigger a refetch (the provider survives navigation).
 */
import { useLocation, useNavigate } from 'react-router-dom';

const ICON_PROPS = {
    width: 12,
    height: 12,
    viewBox: '0 0 14 14',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.6,
    strokeLinecap: 'round',
    'aria-hidden': true,
};

const VIEWS = [
    {
        key: 'table',
        label: 'Table',
        to: '/job-log',
        title: 'Job Log table',
        icon: (
            <svg {...ICON_PROPS}>
                <rect x="1.5" y="2" width="11" height="10" rx="1" />
                <path d="M1.5 5.5h11M1.5 8.75h11M5.5 5.5v6.5" />
            </svg>
        ),
    },
    {
        key: 'timeline',
        label: 'Timeline',
        to: '/pm-board',
        title: 'Install timeline (Gantt)',
        icon: (
            <svg {...ICON_PROPS}>
                <path d="M1.5 3.5h6M3.5 7h7M6 10.5h6.5" strokeWidth="2.2" />
            </svg>
        ),
    },
];

function activeViewFor(location) {
    if (location.pathname.startsWith('/job-log')) return 'table';
    // /pm-board is Timeline-only now (old ?view=timeline deep links land in the same place).
    if (location.pathname.startsWith('/pm-board')) return 'timeline';
    return null;
}

export default function ReleasesViewSwitcher() {
    const location = useLocation();
    const navigate = useNavigate();
    const active = activeViewFor(location);

    return (
        <div
            className="inline-flex rounded-lg border border-gray-300 dark:border-slate-500 overflow-hidden flex-shrink-0 shadow-sm"
            role="tablist"
            aria-label="Release views"
        >
            {VIEWS.map((view, i) => (
                <button
                    key={view.key}
                    type="button"
                    role="tab"
                    aria-selected={active === view.key}
                    title={view.title}
                    onClick={() => {
                        if (active !== view.key) navigate(view.to);
                    }}
                    className={`px-2.5 py-1 text-xs font-semibold transition-all whitespace-nowrap inline-flex items-center gap-1 ${
                        i > 0 ? 'border-l border-gray-300 dark:border-slate-500' : ''
                    } ${
                        active === view.key
                            ? 'bg-blue-700 text-white'
                            : 'bg-white dark:bg-slate-600 text-gray-700 dark:text-slate-200 hover:bg-gray-50 dark:hover:bg-slate-500'
                    }`}
                >
                    {view.icon}
                    {view.label}
                </button>
            ))}
        </div>
    );
}
