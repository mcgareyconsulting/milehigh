/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Monthly invoicing report — every project with billing activity in a chosen month,
 *   expandable into its DRR submittals (create/open/close lifecycle) and releases (stage/install/
 *   invoiced progress) for that month. Gated to khearn + admins.
 * exports:
 *   InvoicingReport: Page component with month/year picker, project filter, CSV export, and
 *     nested expand/collapse cards.
 * imports_from: [react, ../services/invoicingApi, ../utils/auth, ../utils/csv, ../components/ColumnHeaderFilter]
 * imported_by: [frontend/src/App.jsx]
 * invariants:
 *   - Renders an access message (no fetch) unless userCanAccessInvoicing(user) is true.
 *   - Backend already filters to DRR submittals and create/open/close + meaningful release events,
 *     and formats event.created_at as a Mountain-Time string; render it as-is.
 *   - Submittal events carry a `kind` of 'create' | 'open' | 'close' driving the status timeline.
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import { invoicingApi } from '../services/invoicingApi';
import ColumnHeaderFilter from '../components/ColumnHeaderFilter';
import { checkAuth, userCanAccessInvoicing } from '../utils/auth';
import { downloadCsv } from '../utils/csv';

const MONTHS = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
];

// One combined filter value per project: number and name together, e.g. "1201 — Acme Tower".
// project_number is unique, so this label uniquely identifies a project.
const projectLabel = (p) => {
    const name = (p.project_name ?? '').trim();
    return name ? `${p.project_number} — ${name}` : String(p.project_number);
};

// Colors for the release event badges (action-based).
function actionColor(action) {
    if (!action) return 'bg-gray-100 text-gray-800 dark:bg-slate-700 dark:text-slate-200';
    const a = action.toLowerCase();
    const colors = {
        update: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-200',
        updated: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-200',
        update_stage: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900/40 dark:text-indigo-200',
        list_move: 'bg-purple-100 text-purple-800 dark:bg-purple-900/40 dark:text-purple-200',
        created: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-200',
        create: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-200',
        delete: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200',
    };
    return colors[a] || colors[a.split('_')[0]] || 'bg-gray-100 text-gray-800 dark:bg-slate-700 dark:text-slate-200';
}

// Colors + labels for the submittal lifecycle timeline (kind-based).
const KIND_LABEL = { create: 'Created', open: 'Opened', close: 'Closed' };
const KIND_DOT = {
    create: 'bg-green-500',
    open: 'bg-blue-500',
    close: 'bg-slate-500 dark:bg-slate-400',
};

function Chevron({ open }) {
    return (
        <span
            className={`inline-block text-gray-400 dark:text-slate-500 transition-transform duration-150 ${open ? 'rotate-90' : ''}`}
            aria-hidden="true"
        >
            ▸
        </span>
    );
}

// A clickable toggle row used at every level of the tree.
function ToggleRow({ open, onToggle, depthClass, children }) {
    const handleKey = (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onToggle();
        }
    };
    return (
        <div
            role="button"
            tabIndex={0}
            aria-expanded={open}
            onClick={onToggle}
            onKeyDown={handleKey}
            className={`flex items-center gap-2 cursor-pointer hover:bg-gray-50 dark:hover:bg-slate-700/50 focus:outline-none focus:ring-2 focus:ring-accent-500 ${depthClass}`}
        >
            {children}
        </div>
    );
}

// Most recent date string for a given lifecycle kind (events are newest-first).
const kindDate = (events, kind) => {
    const ev = events.find((e) => e.kind === kind);
    return ev ? ev.created_at : null;
};

// DRR submittals as a compact create/open/close timeline table. No expand needed —
// the three lifecycle dates are the whole story for a billing month.
function SubmittalTimeline({ submittals }) {
    if (submittals.length === 0) {
        return (
            <div className="pl-12 pr-3 py-2 text-xs text-gray-500 dark:text-slate-400">
                No DRR submittal activity this month.
            </div>
        );
    }
    return (
        <div className="overflow-x-auto">
            <table className="w-full text-xs">
                <thead>
                    <tr className="text-left text-gray-500 dark:text-slate-400">
                        <th className="pl-12 pr-3 py-1.5 font-medium">DRR Submittal</th>
                        {['create', 'open', 'close'].map((k) => (
                            <th key={k} className="px-3 py-1.5 font-medium whitespace-nowrap w-44">
                                <span className="inline-flex items-center gap-1.5">
                                    <span className={`inline-block w-2 h-2 rounded-full ${KIND_DOT[k]}`} />
                                    {KIND_LABEL[k]}
                                </span>
                            </th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {submittals.map((s) => {
                        const label = `${s.submittal_id}${s.title ? ` — ${s.title}` : ''}`;
                        return (
                            <tr key={s.submittal_id} className="border-t border-gray-100 dark:border-slate-700/70">
                                <td className="pl-12 pr-3 py-2 text-gray-800 dark:text-slate-100">
                                    <span className="block truncate max-w-md" title={label}>{label}</span>
                                    {s.submittal_manager && (
                                        <span className="text-[11px] text-gray-400 dark:text-slate-500">
                                            Mgr: {s.submittal_manager}
                                        </span>
                                    )}
                                </td>
                                {['create', 'open', 'close'].map((k) => {
                                    const d = kindDate(s.events, k);
                                    return (
                                        <td key={k} className="px-3 py-2 whitespace-nowrap text-gray-600 dark:text-slate-300">
                                            {d || <span className="text-gray-300 dark:text-slate-600">—</span>}
                                        </td>
                                    );
                                })}
                            </tr>
                        );
                    })}
                </tbody>
            </table>
        </div>
    );
}

// One release, expandable into its month's change events.
function ReleaseRow({ release, expanded, onToggle }) {
    const r = release;
    const label = `${r.release}${r.description ? ` — ${r.description}` : ''}`;
    const meta = [
        { label: 'Stage', value: r.stage, width: 'w-40' },
        { label: 'Install', value: r.install_prog, width: 'w-24' },
        { label: 'Invoiced', value: r.invoiced, width: 'w-24' },
    ];
    return (
        <div className="border-t border-gray-100 dark:border-slate-700">
            <ToggleRow open={expanded} onToggle={onToggle} depthClass="pl-12 pr-3 py-2">
                <Chevron open={expanded} />
                <span className="flex-1 min-w-0 text-sm text-gray-800 dark:text-slate-100 truncate" title={label}>
                    {label}
                </span>
                <span className="hidden md:flex items-center gap-4 text-[11px] text-gray-500 dark:text-slate-400 shrink-0">
                    {meta.map((m) => (
                        <span key={m.label} className={`${m.width} shrink-0 truncate`}>
                            {m.value != null && m.value !== '' && (
                                <>
                                    <span className="text-gray-400 dark:text-slate-500">{m.label}:</span> {m.value}
                                </>
                            )}
                        </span>
                    ))}
                </span>
                <span className="shrink-0 w-20 text-right text-xs font-medium text-gray-500 dark:text-slate-400 whitespace-nowrap">
                    {r.total_changes} {r.total_changes === 1 ? 'change' : 'changes'}
                </span>
            </ToggleRow>
            {expanded && (
                <ul className="pl-16 pr-3 py-2 space-y-2 bg-gray-50 dark:bg-slate-800/60">
                    {r.events.length === 0 && (
                        <li className="text-xs text-gray-500 dark:text-slate-400">No changes this month.</li>
                    )}
                    {r.events.map((ev) => (
                        <li key={ev.id} className="flex items-center gap-3 text-xs">
                            <span className="w-40 shrink-0">
                                <span className={`inline-block px-2 py-0.5 rounded-full font-medium ${actionColor(ev.action)}`}>
                                    {ev.action}
                                </span>
                            </span>
                            <span className="flex-1 min-w-0 truncate text-gray-800 dark:text-slate-100">
                                {ev.new_value || ''}
                            </span>
                            <span className="shrink-0 text-gray-500 dark:text-slate-400 whitespace-nowrap">
                                {ev.created_at}
                                {ev.source ? ` · ${ev.source}` : ''}
                            </span>
                        </li>
                    ))}
                </ul>
            )}
        </div>
    );
}

function SummaryStat({ value, label }) {
    return (
        <div className="flex flex-col items-center px-3">
            <span className="text-xl font-bold text-gray-900 dark:text-slate-100 leading-none">{value}</span>
            <span className="text-[11px] uppercase tracking-wide text-gray-500 dark:text-slate-400 mt-0.5">{label}</span>
        </div>
    );
}

function InvoicingReport() {
    const now = new Date();
    const [authorized, setAuthorized] = useState(null); // null = checking
    const [year, setYear] = useState(now.getFullYear());
    const [month, setMonth] = useState(now.getMonth() + 1); // 1-based
    const [report, setReport] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const [expandedProjects, setExpandedProjects] = useState(new Set());
    const [expandedItems, setExpandedItems] = useState(new Set());

    // Single combined project filter (Excel-style). Empty Set = no filter.
    const [projectFilter, setProjectFilter] = useState(new Set());
    const [columnSort, setColumnSort] = useState({ column: null, direction: null });

    useEffect(() => {
        checkAuth().then((user) => setAuthorized(userCanAccessInvoicing(user)));
    }, []);

    const fetchReport = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const data = await invoicingApi.fetchMonthlyReport({ year, month });
            setReport(data);
            // Reset expansion when the dataset changes.
            setExpandedProjects(new Set());
            setExpandedItems(new Set());
        } catch (err) {
            setError(err.message);
            setReport(null);
        } finally {
            setLoading(false);
        }
    }, [year, month]);

    useEffect(() => {
        if (authorized) fetchReport();
    }, [authorized, fetchReport]);

    const toggle = (setter) => (key) => {
        setter((prev) => {
            const next = new Set(prev);
            if (next.has(key)) next.delete(key);
            else next.add(key);
            return next;
        });
    };
    const toggleProject = toggle(setExpandedProjects);
    const toggleItem = toggle(setExpandedItems);

    const projects = useMemo(() => report?.projects || [], [report]);

    // Combined project values for the dropdown, sorted by project number.
    const projectValues = useMemo(
        () => projects.map(projectLabel).sort((a, b) => a.localeCompare(b, undefined, { numeric: true })),
        [projects],
    );

    const visibleProjects = useMemo(
        () => projects
            .filter((p) => projectFilter.size === 0 || projectFilter.has(projectLabel(p)))
            .sort((a, b) => {
                if (!columnSort.column) return 0;
                const mult = columnSort.direction === 'desc' ? -1 : 1;
                return mult * projectLabel(a).localeCompare(projectLabel(b), undefined, { numeric: true });
            }),
        [projects, projectFilter, columnSort],
    );

    // Totals across the currently visible projects.
    const totals = useMemo(() => visibleProjects.reduce(
        (acc, p) => {
            acc.submittals += p.submittals.length;
            acc.releases += p.releases.length;
            return acc;
        },
        { submittals: 0, releases: 0 },
    ), [visibleProjects]);

    const exportCsv = useCallback(() => {
        const headers = ['Project #', 'Project', 'Section', 'Item', 'Event', 'Detail', 'Date', 'Source'];
        const rows = [];
        for (const p of visibleProjects) {
            for (const s of p.submittals) {
                const item = `${s.submittal_id}${s.title ? ` — ${s.title}` : ''}`;
                for (const ev of s.events) {
                    rows.push([p.project_number, p.project_name || '', 'DRR Submittal', item,
                        KIND_LABEL[ev.kind] || ev.action, ev.new_value || '', ev.created_at, ev.source || '']);
                }
            }
            for (const r of p.releases) {
                const item = `${r.release}${r.description ? ` — ${r.description}` : ''}`;
                for (const ev of r.events) {
                    rows.push([p.project_number, p.project_name || '', 'Release', item,
                        ev.action, ev.new_value || '', ev.created_at, ev.source || '']);
                }
            }
        }
        downloadCsv(`invoicing-${year}-${String(month).padStart(2, '0')}.csv`, headers, rows);
    }, [visibleProjects, month, year]);

    if (authorized === null) {
        return (
            <div className="flex-1 flex items-center justify-center text-gray-600 dark:text-slate-400">
                Loading…
            </div>
        );
    }

    if (!authorized) {
        return (
            <div className="flex-1 flex items-center justify-center p-6 text-center">
                <div className="text-gray-600 dark:text-slate-400">
                    You don’t have access to the invoicing report.
                </div>
            </div>
        );
    }

    const years = [];
    for (let y = now.getFullYear(); y >= now.getFullYear() - 5; y -= 1) years.push(y);
    const hasData = !loading && !error && visibleProjects.length > 0;

    return (
        <div className="flex-1 w-full max-w-5xl mx-auto p-4 sm:p-6">
            {/* Header: title + month/year picker */}
            <div className="flex flex-wrap items-end gap-3 mb-4">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900 dark:text-slate-100">
                        Invoicing — {report?.month_label || `${MONTHS[month - 1]} ${year}`}
                    </h1>
                    <p className="text-sm text-gray-500 dark:text-slate-400">
                        DRR submittal lifecycle and release progress, grouped by project.
                    </p>
                </div>
                <div className="ml-auto flex items-end gap-2">
                    <label className="flex flex-col text-xs font-medium text-gray-600 dark:text-slate-400">
                        Month
                        <select
                            value={month}
                            onChange={(e) => setMonth(parseInt(e.target.value, 10))}
                            className="mt-1 px-2 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-gray-900 dark:text-slate-100"
                        >
                            {MONTHS.map((m, i) => (
                                <option key={m} value={i + 1}>{m}</option>
                            ))}
                        </select>
                    </label>
                    <label className="flex flex-col text-xs font-medium text-gray-600 dark:text-slate-400">
                        Year
                        <select
                            value={year}
                            onChange={(e) => setYear(parseInt(e.target.value, 10))}
                            className="mt-1 px-2 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-gray-900 dark:text-slate-100"
                        >
                            {years.map((y) => (
                                <option key={y} value={y}>{y}</option>
                            ))}
                        </select>
                    </label>
                </div>
            </div>

            {/* Summary bar: totals + filter + export */}
            {hasData && (
                <div className="flex flex-wrap items-center gap-3 mb-4 p-3 rounded-xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800">
                    <div className="flex items-center divide-x divide-gray-200 dark:divide-slate-700">
                        <SummaryStat value={visibleProjects.length} label="Projects" />
                        <SummaryStat value={totals.submittals} label="DRR" />
                        <SummaryStat value={totals.releases} label="Releases" />
                    </div>
                    <div className="ml-auto flex items-center gap-2">
                        <span className="px-2 py-1 rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-sm">
                            <ColumnHeaderFilter
                                column="project"
                                values={projectValues}
                                hasBlanks={false}
                                selected={projectFilter}
                                onChange={(next) => setProjectFilter(new Set(next))}
                                sort={columnSort}
                                onSort={(dir) => setColumnSort(dir ? { column: 'project', direction: dir } : { column: null, direction: null })}
                                isActive={projectFilter.size > 0}
                                autoWidth
                            >
                                Project # / Name
                            </ColumnHeaderFilter>
                        </span>
                        <button
                            type="button"
                            onClick={exportCsv}
                            className="px-3 py-1.5 text-sm font-medium rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-gray-700 dark:text-slate-200 hover:bg-gray-50 dark:hover:bg-slate-700"
                        >
                            Export CSV
                        </button>
                    </div>
                </div>
            )}

            {loading && (
                <div className="py-12 text-center text-gray-500 dark:text-slate-400">Loading report…</div>
            )}

            {error && !loading && (
                <div className="py-4 px-4 rounded-lg bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-200 text-sm">
                    {error}
                </div>
            )}

            {!loading && !error && projects.length === 0 && (
                <div className="py-12 text-center text-gray-500 dark:text-slate-400">
                    No project activity for {report?.month_label || `${MONTHS[month - 1]} ${year}`}.
                </div>
            )}

            {!loading && !error && projects.length > 0 && visibleProjects.length === 0 && (
                <div className="py-12 text-center text-gray-500 dark:text-slate-400">
                    No projects match the current filters.
                </div>
            )}

            {hasData && (
                <div className="rounded-xl border border-gray-200 dark:border-slate-700 overflow-hidden bg-white dark:bg-slate-800 divide-y divide-gray-200 dark:divide-slate-700">
                    {visibleProjects.map((proj) => {
                        const pKey = proj.project_number;
                        const pOpen = expandedProjects.has(pKey);
                        return (
                            <div key={pKey}>
                                {/* Level 1 — Project */}
                                <ToggleRow open={pOpen} onToggle={() => toggleProject(pKey)} depthClass="px-3 py-3">
                                    <Chevron open={pOpen} />
                                    <span className="font-semibold text-gray-900 dark:text-slate-100">
                                        {proj.project_number}
                                    </span>
                                    <span className="text-gray-600 dark:text-slate-300 truncate">
                                        {proj.project_name || '—'}
                                    </span>
                                    <span className="ml-auto text-xs text-gray-500 dark:text-slate-400 whitespace-nowrap">
                                        {proj.submittals.length} DRR · {proj.releases.length} releases
                                    </span>
                                </ToggleRow>

                                {pOpen && (
                                    <div className="border-t border-gray-100 dark:border-slate-700">
                                        {/* DRR Submittals — lifecycle timeline */}
                                        <div className="py-2 bg-gray-50/60 dark:bg-slate-800/40">
                                            <div className="pl-8 pr-3 pb-1 text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-slate-400">
                                                DRR Submittals
                                            </div>
                                            <SubmittalTimeline submittals={proj.submittals} />
                                        </div>

                                        {/* Releases — expandable event rows */}
                                        <div className="py-2 border-t border-gray-100 dark:border-slate-700">
                                            <div className="pl-8 pr-3 pb-1 text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-slate-400">
                                                Releases
                                            </div>
                                            {proj.releases.length === 0 && (
                                                <div className="pl-12 pr-3 py-2 text-xs text-gray-500 dark:text-slate-400">
                                                    No release activity this month.
                                                </div>
                                            )}
                                            {proj.releases.map((r) => {
                                                const key = `${pKey}:rel:${r.job}-${r.release}`;
                                                return (
                                                    <ReleaseRow
                                                        key={key}
                                                        release={r}
                                                        expanded={expandedItems.has(key)}
                                                        onToggle={() => toggleItem(key)}
                                                    />
                                                );
                                            })}
                                        </div>
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}

export default InvoicingReport;
