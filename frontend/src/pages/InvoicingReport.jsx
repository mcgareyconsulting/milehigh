/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Monthly invoicing report — every project with billing activity in a chosen month,
 *   expandable into its DRR submittals (create/open/close lifecycle) and releases (stage/install/
 *   invoiced progress) for that month. Gated to khearn + admins.
 * exports:
 *   InvoicingReport: Page component with month/year picker, project filter, CSV export, and
 *     nested expand/collapse cards.
 * imports_from: [react, ../services/invoicingApi, ../utils/auth, ../utils/csv, ../utils/stageProgress,
 *   ../components/ColumnHeaderFilter]
 * imported_by: [frontend/src/App.jsx]
 * invariants:
 *   - Renders an access message (no fetch) unless userCanAccessInvoicing(user) is true.
 *   - Backend already filters to DRR submittals and create/open/close + meaningful release events,
 *     and formats event.created_at as a Mountain-Time string ("May 04, 2026 07:32:15 AM").
 *   - Submittal events carry a `kind` of 'create' | 'open' | 'close' driving the status timeline.
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import { invoicingApi } from '../services/invoicingApi';
import ColumnHeaderFilter from '../components/ColumnHeaderFilter';
import { checkAuth, userCanAccessInvoicing } from '../utils/auth';
import { downloadCsv } from '../utils/csv';
import { isCompleteStage } from '../utils/stageProgress';

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

// ---------------------------------------------------------------------------
// Date formatting — the backend sends "May 04, 2026 07:32:15 AM" (Mountain).
// Split it into a tidy date + time so the timeline reads cleanly.
// ---------------------------------------------------------------------------
function splitDateTime(s) {
    if (!s) return { date: '', time: '' };
    const m = String(s).match(/^(.*?\d{4})\s+(.*)$/);
    return m ? { date: m[1], time: m[2] } : { date: String(s), time: '' };
}
// "May 04, 2026" -> "May 4, 2026"
const prettyDate = (s) => splitDateTime(s).date.replace(/\b0(\d),/, '$1,');
// "07:32:15 AM" -> "7:32 AM"
const prettyTime = (s) => splitDateTime(s).time.replace(/:\d{2}\s/, ' ').replace(/^0/, '');

// ---------------------------------------------------------------------------
// Color tokens — tinted, ring-bordered badges that work in light + dark.
// ---------------------------------------------------------------------------
const TINT = {
    emerald: 'bg-emerald-50 text-emerald-700 ring-emerald-200/70 dark:bg-emerald-500/10 dark:text-emerald-300 dark:ring-emerald-500/30',
    blue: 'bg-blue-50 text-blue-700 ring-blue-200/70 dark:bg-blue-500/10 dark:text-blue-300 dark:ring-blue-500/30',
    violet: 'bg-violet-50 text-violet-700 ring-violet-200/70 dark:bg-violet-500/10 dark:text-violet-300 dark:ring-violet-500/30',
    amber: 'bg-amber-50 text-amber-700 ring-amber-200/70 dark:bg-amber-500/10 dark:text-amber-300 dark:ring-amber-500/30',
    orange: 'bg-orange-50 text-orange-700 ring-orange-200/70 dark:bg-orange-500/10 dark:text-orange-300 dark:ring-orange-500/30',
    purple: 'bg-purple-50 text-purple-700 ring-purple-200/70 dark:bg-purple-500/10 dark:text-purple-300 dark:ring-purple-500/30',
    red: 'bg-red-50 text-red-700 ring-red-200/70 dark:bg-red-500/10 dark:text-red-300 dark:ring-red-500/30',
    slate: 'bg-slate-100 text-slate-600 ring-slate-200/80 dark:bg-slate-500/10 dark:text-slate-300 dark:ring-slate-500/30',
    accent: 'bg-accent-50 text-accent-600 ring-accent-200/70 dark:bg-accent-400/10 dark:text-accent-200 dark:ring-accent-400/30',
};

// Solid dots used as section/legend markers.
const KIND_META = {
    create: { label: 'Created', tint: 'emerald', dot: 'bg-emerald-500' },
    open: { label: 'Opened', tint: 'blue', dot: 'bg-blue-500' },
    close: { label: 'Closed', tint: 'slate', dot: 'bg-slate-400 dark:bg-slate-500' },
};

// Stage → color family, mirroring the Job Log's fab progression.
function stageTint(stage) {
    const s = (stage || '').toLowerCase();
    if (isCompleteStage(stage)) return 'emerald';
    if (s.includes('hold')) return 'red';
    if (s.includes('install') || s.includes('ship')) return 'blue';
    if (s.includes('paint') || s.includes('store')) return 'violet';
    if (s.includes('weld') || s.includes('qc')) return 'amber';
    if (s.includes('fitup') || s.includes('cut') || s.includes('material')) return 'orange';
    return 'slate';
}

// Release event action → color family.
function actionTint(action) {
    const a = (action || '').toLowerCase();
    if (a.startsWith('create')) return 'emerald';
    if (a.startsWith('delete')) return 'red';
    if (a.includes('stage')) return 'accent';
    if (a.includes('list_move')) return 'purple';
    if (a.includes('install') || a.includes('ship')) return 'blue';
    if (a.includes('pickup') || a.includes('received')) return 'amber';
    return 'slate';
}

function Badge({ tint = 'slate', dot = false, className = '', children }) {
    return (
        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium ring-1 ring-inset ${TINT[tint]} ${className}`}>
            {dot && <span className={`w-1.5 h-1.5 rounded-full ${KIND_META[dot]?.dot || 'bg-current'}`} />}
            {children}
        </span>
    );
}

function Chevron({ open }) {
    return (
        <span
            className={`inline-block text-gray-400 dark:text-slate-500 transition-transform duration-200 ${open ? 'rotate-90' : ''}`}
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
            className={`flex items-center gap-2 cursor-pointer transition-colors hover:bg-gray-50 dark:hover:bg-slate-700/40 focus:outline-none focus:ring-2 focus:ring-inset focus:ring-accent-400/60 ${depthClass}`}
        >
            {children}
        </div>
    );
}

// Most recent event of a given lifecycle kind (events arrive newest-first).
const kindEvent = (events, kind) => events.find((e) => e.kind === kind) || null;

// A single timeline cell: a colored date chip + muted time, or a soft dash.
function TimelineCell({ event, kind }) {
    if (!event) {
        return (
            <td className="px-3 py-2.5 align-top">
                <span className="text-gray-300 dark:text-slate-600 select-none">—</span>
            </td>
        );
    }
    const meta = KIND_META[kind];
    return (
        <td className="px-3 py-2.5 align-top whitespace-nowrap">
            <span className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-lg text-xs font-medium ring-1 ring-inset ${TINT[meta.tint]}`}>
                <span className={`w-1.5 h-1.5 rounded-full ${meta.dot}`} />
                {prettyDate(event.created_at)}
            </span>
            <div className="mt-0.5 pl-1 text-[10px] text-gray-400 dark:text-slate-500">{prettyTime(event.created_at)}</div>
        </td>
    );
}

// DRR submittals rendered as a create/open/close lifecycle table.
function SubmittalTimeline({ submittals }) {
    if (submittals.length === 0) {
        return (
            <div className="px-6 py-3 text-xs text-gray-400 dark:text-slate-500 italic">
                No DRR submittal activity this month.
            </div>
        );
    }
    return (
        <div className="overflow-x-auto">
            <table className="w-full text-sm">
                <thead>
                    <tr className="text-left text-[11px] uppercase tracking-wide text-gray-400 dark:text-slate-500">
                        <th className="pl-12 pr-3 py-1.5 font-semibold">DRR Submittal</th>
                        {['create', 'open', 'close'].map((k) => (
                            <th key={k} className="px-3 py-1.5 font-semibold w-44">
                                <span className="inline-flex items-center gap-1.5">
                                    <span className={`inline-block w-2 h-2 rounded-full ${KIND_META[k].dot}`} />
                                    {KIND_META[k].label}
                                </span>
                            </th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {submittals.map((s) => {
                        const label = `${s.submittal_id}${s.title ? ` — ${s.title}` : ''}`;
                        return (
                            <tr key={s.submittal_id} className="border-t border-gray-100 dark:border-slate-700/60 hover:bg-gray-50/70 dark:hover:bg-slate-700/30">
                                <td className="pl-12 pr-3 py-2.5 align-top">
                                    <span className="block truncate max-w-md text-gray-800 dark:text-slate-100" title={label}>{label}</span>
                                    {s.submittal_manager && (
                                        <span className="text-[11px] text-gray-400 dark:text-slate-500">{s.submittal_manager}</span>
                                    )}
                                </td>
                                {['create', 'open', 'close'].map((k) => (
                                    <TimelineCell key={k} event={kindEvent(s.events, k)} kind={k} />
                                ))}
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
    return (
        <div className="border-t border-gray-100 dark:border-slate-700/60">
            <ToggleRow open={expanded} onToggle={onToggle} depthClass="pl-12 pr-3 py-2.5">
                <Chevron open={expanded} />
                <span className="flex-1 min-w-0 text-sm text-gray-800 dark:text-slate-100 truncate" title={label}>
                    {label}
                </span>
                <span className="hidden md:flex items-center gap-2 shrink-0">
                    {r.stage && <Badge tint={stageTint(r.stage)}>{r.stage}</Badge>}
                    {r.install_prog != null && r.install_prog !== '' && (
                        <span className="text-[11px] text-gray-400 dark:text-slate-500">
                            Install <span className="font-semibold text-gray-600 dark:text-slate-300">{r.install_prog}</span>
                        </span>
                    )}
                    {r.invoiced != null && r.invoiced !== '' && (
                        <span className="text-[11px] text-gray-400 dark:text-slate-500">
                            Inv <span className="font-semibold text-gray-600 dark:text-slate-300">{r.invoiced}</span>
                        </span>
                    )}
                </span>
                <span className="shrink-0 w-20 text-right text-[11px] font-medium text-gray-400 dark:text-slate-500 whitespace-nowrap">
                    {r.total_changes} {r.total_changes === 1 ? 'change' : 'changes'}
                </span>
            </ToggleRow>
            {expanded && (
                <ul className="pl-16 pr-3 py-2 space-y-1.5 bg-gray-50/80 dark:bg-slate-900/40 border-t border-gray-100 dark:border-slate-700/60">
                    {r.events.length === 0 && (
                        <li className="text-xs text-gray-400 dark:text-slate-500 italic">No changes this month.</li>
                    )}
                    {r.events.map((ev) => (
                        <li key={ev.id} className="flex items-center gap-3 text-xs">
                            <span className="w-44 shrink-0">
                                <Badge tint={actionTint(ev.action)}>{ev.action}</Badge>
                            </span>
                            <span className="flex-1 min-w-0 truncate text-gray-700 dark:text-slate-200">
                                {ev.new_value || ''}
                            </span>
                            <span className="shrink-0 text-gray-400 dark:text-slate-500 whitespace-nowrap">
                                {prettyDate(ev.created_at)} · {prettyTime(ev.created_at)}
                                {ev.source ? ` · ${ev.source}` : ''}
                            </span>
                        </li>
                    ))}
                </ul>
            )}
        </div>
    );
}

function SummaryStat({ value, label, tint }) {
    return (
        <div className="flex items-center gap-2.5 px-4">
            <span className={`w-2.5 h-2.5 rounded-full ${tint}`} />
            <div className="flex flex-col leading-none">
                <span className="text-2xl font-bold text-gray-900 dark:text-slate-50 tabular-nums">{value}</span>
                <span className="text-[10px] uppercase tracking-widest text-gray-400 dark:text-slate-500 mt-1">{label}</span>
            </div>
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
                        KIND_META[ev.kind]?.label || ev.action, ev.new_value || '', ev.created_at, ev.source || '']);
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
    const selectClass = 'mt-1 px-2.5 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-gray-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-accent-400/60';

    return (
        <div className="flex-1 w-full max-w-5xl mx-auto p-4 sm:p-6">
            {/* Header: title + month/year picker */}
            <div className="flex flex-wrap items-end gap-3 mb-4">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900 dark:text-slate-50">
                        Invoicing <span className="text-accent-500 dark:text-accent-300">— {report?.month_label || `${MONTHS[month - 1]} ${year}`}</span>
                    </h1>
                    <p className="text-sm text-gray-500 dark:text-slate-400">
                        DRR submittal lifecycle and release progress, grouped by project.
                    </p>
                </div>
                <div className="ml-auto flex items-end gap-2">
                    <label className="flex flex-col text-xs font-medium text-gray-600 dark:text-slate-400">
                        Month
                        <select value={month} onChange={(e) => setMonth(parseInt(e.target.value, 10))} className={selectClass}>
                            {MONTHS.map((m, i) => (<option key={m} value={i + 1}>{m}</option>))}
                        </select>
                    </label>
                    <label className="flex flex-col text-xs font-medium text-gray-600 dark:text-slate-400">
                        Year
                        <select value={year} onChange={(e) => setYear(parseInt(e.target.value, 10))} className={selectClass}>
                            {years.map((y) => (<option key={y} value={y}>{y}</option>))}
                        </select>
                    </label>
                </div>
            </div>

            {/* Summary bar: totals + filter + export */}
            {hasData && (
                <div className="flex flex-wrap items-center gap-3 mb-5 p-3 rounded-2xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 shadow-sm">
                    <div className="flex items-center divide-x divide-gray-200 dark:divide-slate-700">
                        <SummaryStat value={visibleProjects.length} label="Projects" tint="bg-accent-500" />
                        <SummaryStat value={totals.submittals} label="DRR" tint="bg-emerald-500" />
                        <SummaryStat value={totals.releases} label="Releases" tint="bg-blue-500" />
                    </div>
                    <div className="ml-auto flex items-center gap-2">
                        <span className="px-2.5 py-1.5 rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-sm">
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
                            className="inline-flex items-center gap-1.5 px-3.5 py-2 text-sm font-semibold rounded-lg bg-accent-500 text-white shadow-sm hover:bg-accent-600 focus:outline-none focus:ring-2 focus:ring-accent-400/60 transition-colors"
                        >
                            <span aria-hidden="true">↓</span> Export CSV
                        </button>
                    </div>
                </div>
            )}

            {loading && (
                <div className="py-16 text-center text-gray-500 dark:text-slate-400">Loading report…</div>
            )}

            {error && !loading && (
                <div className="py-4 px-4 rounded-xl bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-200 text-sm ring-1 ring-red-200/60 dark:ring-red-500/30">
                    {error}
                </div>
            )}

            {!loading && !error && projects.length === 0 && (
                <div className="py-16 text-center text-gray-500 dark:text-slate-400">
                    No project activity for {report?.month_label || `${MONTHS[month - 1]} ${year}`}.
                </div>
            )}

            {!loading && !error && projects.length > 0 && visibleProjects.length === 0 && (
                <div className="py-16 text-center text-gray-500 dark:text-slate-400">
                    No projects match the current filters.
                </div>
            )}

            {hasData && (
                <div className="rounded-2xl border border-gray-200 dark:border-slate-700 overflow-hidden bg-white dark:bg-slate-800 shadow-sm divide-y divide-gray-100 dark:divide-slate-700/70">
                    {visibleProjects.map((proj) => {
                        const pKey = proj.project_number;
                        const pOpen = expandedProjects.has(pKey);
                        return (
                            <div key={pKey} className={pOpen ? 'bg-gray-50/40 dark:bg-slate-800/60' : ''}>
                                {/* Level 1 — Project */}
                                <ToggleRow open={pOpen} onToggle={() => toggleProject(pKey)} depthClass="px-3 py-3">
                                    <Chevron open={pOpen} />
                                    <span className="px-2 py-0.5 rounded-md text-sm font-bold font-mono bg-accent-50 text-accent-700 dark:bg-accent-400/10 dark:text-accent-200 ring-1 ring-inset ring-accent-200/60 dark:ring-accent-400/20">
                                        {proj.project_number}
                                    </span>
                                    <span className="text-gray-700 dark:text-slate-200 font-medium truncate">
                                        {proj.project_name || '—'}
                                    </span>
                                    <span className="ml-auto flex items-center gap-2 shrink-0">
                                        <Badge tint={proj.submittals.length ? 'emerald' : 'slate'} className={proj.submittals.length ? '' : 'opacity-60'}>
                                            {proj.submittals.length} DRR
                                        </Badge>
                                        <Badge tint={proj.releases.length ? 'blue' : 'slate'} className={proj.releases.length ? '' : 'opacity-60'}>
                                            {proj.releases.length} rel
                                        </Badge>
                                    </span>
                                </ToggleRow>

                                {pOpen && (
                                    <div className="border-t border-gray-100 dark:border-slate-700/60">
                                        {/* DRR Submittals — lifecycle timeline */}
                                        <div className="py-2.5">
                                            <div className="pl-8 pr-3 pb-1 text-[11px] font-bold uppercase tracking-widest text-gray-400 dark:text-slate-500">
                                                DRR Submittals
                                            </div>
                                            <SubmittalTimeline submittals={proj.submittals} />
                                        </div>

                                        {/* Releases — expandable event rows */}
                                        <div className="py-2.5 border-t border-gray-100 dark:border-slate-700/60">
                                            <div className="pl-8 pr-3 pb-1 text-[11px] font-bold uppercase tracking-widest text-gray-400 dark:text-slate-500">
                                                Releases
                                            </div>
                                            {proj.releases.length === 0 && (
                                                <div className="px-6 py-2 text-xs text-gray-400 dark:text-slate-500 italic">
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
