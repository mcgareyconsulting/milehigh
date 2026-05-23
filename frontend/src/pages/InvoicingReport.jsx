/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Monthly invoicing report — every project with activity in a chosen month, expandable into its
 *   submittals and releases and their change history for that month. Gated to khearn + admins.
 * exports:
 *   InvoicingReport: Page component with month/year picker and nested expand/collapse rows.
 * imports_from: [react, ../services/invoicingApi, ../utils/auth]
 * imported_by: [frontend/src/App.jsx]
 * invariants:
 *   - Renders an access message (no fetch) unless userCanAccessInvoicing(user) is true.
 *   - Backend already formats event.created_at as a Mountain-Time string; render it as-is.
 *   - Only projects/items with changes in the selected month are returned by the API.
 */
import { useState, useEffect, useCallback } from 'react';
import { invoicingApi } from '../services/invoicingApi';
import { checkAuth, userCanAccessInvoicing } from '../utils/auth';

const MONTHS = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
];

function actionColor(action) {
    if (!action) return 'bg-gray-100 text-gray-800 dark:bg-slate-700 dark:text-slate-200';
    const a = action.toLowerCase();
    const colors = {
        update: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-200',
        updated: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-200',
        update_stage: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-200',
        create: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-200',
        created: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-200',
        delete: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200',
        list_move: 'bg-purple-100 text-purple-800 dark:bg-purple-900/40 dark:text-purple-200',
    };
    return colors[a] || colors[a.split('_')[0]] || 'bg-gray-100 text-gray-800 dark:bg-slate-700 dark:text-slate-200';
}

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

// One submittal/release item, expandable into its month's change history.
// `meta` is an array of { label, value, width } summary fields rendered as fixed-width
// columns so they align vertically across rows; empty values keep their slot.
function ItemRow({ label, meta = [], totalChanges, events, expanded, onToggle }) {
    return (
        <div className="border-t border-gray-100 dark:border-slate-700">
            <ToggleRow open={expanded} onToggle={onToggle} depthClass="pl-12 pr-3 py-2">
                <Chevron open={expanded} />
                <span className="flex-1 min-w-0 text-sm text-gray-800 dark:text-slate-100 truncate" title={label}>
                    {label}
                </span>
                {meta.length > 0 && (
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
                )}
                <span className="shrink-0 w-20 text-right text-xs font-medium text-gray-500 dark:text-slate-400 whitespace-nowrap">
                    {totalChanges} {totalChanges === 1 ? 'change' : 'changes'}
                </span>
            </ToggleRow>
            {expanded && (
                <ul className="pl-16 pr-3 py-2 space-y-2 bg-gray-50 dark:bg-slate-800/60">
                    {events.length === 0 && (
                        <li className="text-xs text-gray-500 dark:text-slate-400">No changes this month.</li>
                    )}
                    {events.map((ev) => (
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

function InvoicingReport() {
    const now = new Date();
    const [authorized, setAuthorized] = useState(null); // null = checking
    const [year, setYear] = useState(now.getFullYear());
    const [month, setMonth] = useState(now.getMonth() + 1); // 1-based
    const [report, setReport] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const [expandedProjects, setExpandedProjects] = useState(new Set());
    const [expandedSections, setExpandedSections] = useState(new Set());
    const [expandedItems, setExpandedItems] = useState(new Set());

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
            setExpandedSections(new Set());
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
    const toggleSection = toggle(setExpandedSections);
    const toggleItem = toggle(setExpandedItems);

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

    const projects = report?.projects || [];
    const years = [];
    for (let y = now.getFullYear(); y >= now.getFullYear() - 5; y -= 1) years.push(y);

    return (
        <div className="flex-1 w-full max-w-5xl mx-auto p-4 sm:p-6">
            <div className="flex flex-wrap items-end gap-3 mb-5">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900 dark:text-slate-100">Invoicing Report</h1>
                    <p className="text-sm text-gray-500 dark:text-slate-400">
                        Monthly change history for releases and submittals, grouped by project.
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

            {!loading && !error && projects.length > 0 && (
                <div className="rounded-xl border border-gray-200 dark:border-slate-700 overflow-hidden bg-white dark:bg-slate-800 divide-y divide-gray-200 dark:divide-slate-700">
                    {projects.map((proj) => {
                        const pKey = proj.project_number;
                        const pOpen = expandedProjects.has(pKey);
                        const subSectionKey = `${pKey}:submittals`;
                        const relSectionKey = `${pKey}:releases`;
                        const subOpen = expandedSections.has(subSectionKey);
                        const relOpen = expandedSections.has(relSectionKey);
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
                                        {proj.submittals.length} submittals · {proj.releases.length} releases
                                    </span>
                                </ToggleRow>

                                {pOpen && (
                                    <div>
                                        {/* Level 2 — Submittals */}
                                        <div className="border-t border-gray-100 dark:border-slate-700">
                                            <ToggleRow open={subOpen} onToggle={() => toggleSection(subSectionKey)} depthClass="pl-8 pr-3 py-2 bg-gray-50/60 dark:bg-slate-800/40">
                                                <Chevron open={subOpen} />
                                                <span className="text-sm font-medium text-gray-700 dark:text-slate-200">
                                                    Submittals
                                                </span>
                                                <span className="ml-auto text-xs text-gray-500 dark:text-slate-400">
                                                    {proj.submittals.length}
                                                </span>
                                            </ToggleRow>
                                            {subOpen && proj.submittals.map((s) => {
                                                const key = `${pKey}:sub:${s.submittal_id}`;
                                                const label = `${s.submittal_id}${s.title ? ` — ${s.title}` : ''}`;
                                                const meta = [
                                                    { label: 'Status', value: s.status, width: 'w-40' },
                                                    { label: 'BIC', value: s.ball_in_court, width: 'w-44' },
                                                    { label: 'Sub Mgr', value: s.submittal_manager, width: 'w-44' },
                                                ];
                                                return (
                                                    <ItemRow
                                                        key={key}
                                                        label={label}
                                                        meta={meta}
                                                        totalChanges={s.total_changes}
                                                        events={s.events}
                                                        expanded={expandedItems.has(key)}
                                                        onToggle={() => toggleItem(key)}
                                                    />
                                                );
                                            })}
                                            {subOpen && proj.submittals.length === 0 && (
                                                <div className="pl-12 pr-3 py-2 text-xs text-gray-500 dark:text-slate-400 border-t border-gray-100 dark:border-slate-700">
                                                    No submittal changes this month.
                                                </div>
                                            )}
                                        </div>

                                        {/* Level 2 — Releases */}
                                        <div className="border-t border-gray-100 dark:border-slate-700">
                                            <ToggleRow open={relOpen} onToggle={() => toggleSection(relSectionKey)} depthClass="pl-8 pr-3 py-2 bg-gray-50/60 dark:bg-slate-800/40">
                                                <Chevron open={relOpen} />
                                                <span className="text-sm font-medium text-gray-700 dark:text-slate-200">
                                                    Releases
                                                </span>
                                                <span className="ml-auto text-xs text-gray-500 dark:text-slate-400">
                                                    {proj.releases.length}
                                                </span>
                                            </ToggleRow>
                                            {relOpen && proj.releases.map((r) => {
                                                const key = `${pKey}:rel:${r.job}-${r.release}`;
                                                const label = `${r.release}${r.description ? ` — ${r.description}` : ''}`;
                                                const meta = [
                                                    { label: 'PM', value: r.pm, width: 'w-16' },
                                                    { label: 'Stage', value: r.stage, width: 'w-40' },
                                                    { label: 'Install', value: r.install_prog, width: 'w-24' },
                                                    { label: 'Invoiced', value: r.invoiced, width: 'w-28' },
                                                ];
                                                return (
                                                    <ItemRow
                                                        key={key}
                                                        label={label}
                                                        meta={meta}
                                                        totalChanges={r.total_changes}
                                                        events={r.events}
                                                        expanded={expandedItems.has(key)}
                                                        onToggle={() => toggleItem(key)}
                                                    />
                                                );
                                            })}
                                            {relOpen && proj.releases.length === 0 && (
                                                <div className="pl-12 pr-3 py-2 text-xs text-gray-500 dark:text-slate-400 border-t border-gray-100 dark:border-slate-700">
                                                    No release changes this month.
                                                </div>
                                            )}
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
