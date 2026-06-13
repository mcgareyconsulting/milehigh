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
import ReleaseHistoryModal from '../components/ReleaseHistoryModal';
import Badge from '../components/Badge';
import { checkAuth, userCanAccessInvoicing } from '../utils/auth';
import { downloadCsv } from '../utils/csv';
import {
    TINT, KIND_META, stageTint, prettyDate, prettyTime,
} from '../utils/invoicingFormat';

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

function Chevron({ open }) {
    return (
        <span
            className={`inline-block text-lg text-gray-400 dark:text-slate-500 transition-transform duration-200 ${open ? 'rotate-90' : ''}`}
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
            <td className="px-4 py-4 align-top">
                <span className="text-xl text-gray-300 dark:text-slate-600 select-none">—</span>
            </td>
        );
    }
    const meta = KIND_META[kind];
    return (
        <td className="px-4 py-4 align-top whitespace-nowrap">
            <span className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-base font-medium ring-1 ring-inset ${TINT[meta.tint]}`}>
                <span className={`w-2 h-2 rounded-full ${meta.dot}`} />
                {prettyDate(event.created_at)}
            </span>
            <div className="mt-1 pl-1 text-xs text-gray-400 dark:text-slate-500">{prettyTime(event.created_at)}</div>
        </td>
    );
}

// DRR submittals rendered as a create/open/close lifecycle table.
function SubmittalTimeline({ submittals }) {
    if (submittals.length === 0) {
        return (
            <div className="px-8 py-4 text-sm text-gray-400 dark:text-slate-500 italic">
                No DRR submittal activity this month.
            </div>
        );
    }
    return (
        <div className="overflow-x-auto">
            <table className="w-full text-base">
                <thead>
                    <tr className="text-left text-xs uppercase tracking-wide text-gray-600 dark:text-slate-300">
                        <th className="pl-14 pr-4 py-2.5 font-semibold">DRR Submittal</th>
                        {['create', 'close'].map((k) => (
                            <th key={k} className="px-4 py-2.5 font-semibold w-52">
                                <span className="inline-flex items-center gap-2">
                                    <span className={`inline-block w-2.5 h-2.5 rounded-full ${KIND_META[k].dot}`} />
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
                            <tr key={s.submittal_id} className="border-t border-gray-300 dark:border-slate-600 hover:bg-gray-50/70 dark:hover:bg-slate-700/30">
                                <td className="pl-14 pr-4 py-4 align-top">
                                    <span className="block truncate max-w-xl text-gray-800 dark:text-slate-100" title={label}>{label}</span>
                                    {s.submittal_manager && (
                                        <span className="text-sm text-gray-400 dark:text-slate-500">{s.submittal_manager}</span>
                                    )}
                                </td>
                                {['create', 'close'].map((k) => (
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

// One release — a flat row carrying all billing data plus a History button.
function ReleaseRow({ release, onOpenHistory }) {
    const r = release;
    const label = `${r.release}${r.description ? ` — ${r.description}` : ''}`;
    return (
        <div className="flex items-center gap-2 border-t border-gray-300 dark:border-slate-600 pl-14 pr-4 py-3.5">
            {/* Left: release identity */}
            <span className="flex-1 min-w-0 text-base text-gray-800 dark:text-slate-100 truncate" title={label}>
                {label}
            </span>
            {/* Center: current stage + when it entered that stage */}
            <span className="hidden md:flex items-center gap-3 shrink-0 text-sm">
                <span className="w-40 flex justify-center">
                    {r.stage
                        ? <Badge tint={stageTint(r.stage)} className="w-40 justify-center whitespace-nowrap">{r.stage}</Badge>
                        : <span className="text-gray-400 dark:text-slate-500">—</span>}
                </span>
                <span className="w-32 text-gray-500 dark:text-slate-400 whitespace-nowrap">
                    Since <span className="font-semibold text-gray-700 dark:text-slate-200">
                        {r.stage_entered_at ? prettyDate(r.stage_entered_at) : <span className="text-gray-400 dark:text-slate-500 font-normal">—</span>}
                    </span>
                </span>
            </span>
            {/* Right: install / invoiced + history (flex-1 mirrors the left zone so the center stays centered) */}
            <span className="flex-1 flex items-center justify-end gap-4 text-sm">
                <span className="hidden md:flex items-center gap-4">
                    <span className="w-28 text-gray-500 dark:text-slate-400 whitespace-nowrap">
                        Install <span className="font-semibold text-gray-700 dark:text-slate-200">
                            {r.install_prog || <span className="text-gray-400 dark:text-slate-500 font-normal">—</span>}
                        </span>
                    </span>
                    <span className="w-36 text-gray-500 dark:text-slate-400 whitespace-nowrap">
                        Invoiced <span className="font-semibold text-gray-700 dark:text-slate-200">
                            {r.invoiced || <span className="text-gray-400 dark:text-slate-500 font-normal">—</span>}
                        </span>
                    </span>
                </span>
                <button
                    type="button"
                    onClick={() => onOpenHistory(r)}
                    className="shrink-0 inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-lg border border-gray-300 dark:border-slate-600 text-gray-600 dark:text-slate-300 bg-white dark:bg-slate-800 hover:bg-gray-50 dark:hover:bg-slate-700 focus:outline-none focus:ring-2 focus:ring-accent-400/60 transition-colors"
                >
                    <span aria-hidden="true">🕑</span> History
                </button>
            </span>
        </div>
    );
}

function SummaryStat({ value, label, tint }) {
    return (
        <div className="flex flex-col px-5">
            <div className="flex items-center gap-2 leading-none">
                <span className={`w-2.5 h-2.5 rounded-full ${tint}`} />
                <span className="text-3xl font-bold text-gray-900 dark:text-slate-50 tabular-nums">{value}</span>
            </div>
            <span className="text-xs uppercase tracking-widest text-gray-400 dark:text-slate-500 mt-1.5 pl-[18px]">{label}</span>
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
    const [historyRelease, setHistoryRelease] = useState(null);

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
    const selectClass = 'mt-1.5 px-3 py-2 text-base rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-gray-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-accent-400/60';

    return (
        <div className="flex-1 w-full max-w-[1600px] mx-auto p-6 sm:p-8">
            {/* Header: title + month/year picker */}
            <div className="flex flex-wrap items-end gap-3 mb-6">
                <div>
                    <h1 className="text-3xl font-bold text-gray-900 dark:text-slate-50">
                        Invoicing <span className="text-accent-500 dark:text-accent-300">— {report?.month_label || `${MONTHS[month - 1]} ${year}`}</span>
                    </h1>
                    <p className="text-base text-gray-500 dark:text-slate-400 mt-1">
                        DRR submittal lifecycle and release progress, grouped by project.
                    </p>
                </div>
                <div className="ml-auto flex items-end gap-3">
                    <label className="flex flex-col text-sm font-medium text-gray-600 dark:text-slate-400">
                        Month
                        <select value={month} onChange={(e) => setMonth(parseInt(e.target.value, 10))} className={selectClass}>
                            {MONTHS.map((m, i) => (<option key={m} value={i + 1}>{m}</option>))}
                        </select>
                    </label>
                    <label className="flex flex-col text-sm font-medium text-gray-600 dark:text-slate-400">
                        Year
                        <select value={year} onChange={(e) => setYear(parseInt(e.target.value, 10))} className={selectClass}>
                            {years.map((y) => (<option key={y} value={y}>{y}</option>))}
                        </select>
                    </label>
                </div>
            </div>

            {/* Summary bar: totals + filter + export */}
            {hasData && (
                <div className="flex flex-wrap items-center gap-4 mb-6 p-5 rounded-2xl border border-gray-300 dark:border-slate-700 bg-white dark:bg-slate-800 shadow-sm">
                    <div className="flex items-center divide-x divide-gray-200 dark:divide-slate-700">
                        <SummaryStat value={visibleProjects.length} label="Projects" tint="bg-accent-500" />
                        <SummaryStat value={totals.submittals} label="DRR" tint="bg-emerald-500" />
                        <SummaryStat value={totals.releases} label="Releases" tint="bg-blue-500" />
                    </div>
                    <div className="ml-auto flex items-center gap-3">
                        <span className="px-3 py-2 rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-base">
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
                            className="inline-flex items-center gap-2 px-5 py-2.5 text-base font-semibold rounded-lg bg-accent-500 text-white shadow-sm hover:bg-accent-600 focus:outline-none focus:ring-2 focus:ring-accent-400/60 transition-colors"
                        >
                            <span aria-hidden="true">↓</span> Export CSV
                        </button>
                    </div>
                </div>
            )}

            {loading && (
                <div className="py-20 text-center text-lg text-gray-500 dark:text-slate-400">Loading report…</div>
            )}

            {error && !loading && (
                <div className="py-4 px-5 rounded-xl bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-200 text-base ring-1 ring-red-200/60 dark:ring-red-500/30">
                    {error}
                </div>
            )}

            {!loading && !error && projects.length === 0 && (
                <div className="py-20 text-center text-lg text-gray-500 dark:text-slate-400">
                    No project activity for {report?.month_label || `${MONTHS[month - 1]} ${year}`}.
                </div>
            )}

            {!loading && !error && projects.length > 0 && visibleProjects.length === 0 && (
                <div className="py-20 text-center text-lg text-gray-500 dark:text-slate-400">
                    No projects match the current filters.
                </div>
            )}

            {hasData && (
                <div className="rounded-2xl border border-gray-300 dark:border-slate-700 overflow-hidden bg-white dark:bg-slate-800 shadow-sm divide-y divide-gray-300 dark:divide-slate-600">
                    {visibleProjects.map((proj) => {
                        const pKey = proj.project_number;
                        const pOpen = expandedProjects.has(pKey);
                        return (
                            <div key={pKey} className={pOpen ? 'bg-gray-50/40 dark:bg-slate-800/60' : ''}>
                                {/* Level 1 — Project */}
                                <ToggleRow open={pOpen} onToggle={() => toggleProject(pKey)} depthClass="px-4 py-3.5">
                                    <Chevron open={pOpen} />
                                    <span className="px-2.5 py-1 rounded-md text-base font-bold font-mono bg-accent-50 text-accent-700 dark:bg-accent-400/10 dark:text-accent-200 ring-1 ring-inset ring-accent-200/60 dark:ring-accent-400/20">
                                        {proj.project_number}
                                    </span>
                                    <span className="text-base text-gray-700 dark:text-slate-200 font-medium truncate">
                                        {proj.project_name || '—'}
                                    </span>
                                    <span className="ml-auto flex items-center gap-3 shrink-0">
                                        <Badge tint={proj.submittals.length ? 'emerald' : 'slate'} className={proj.submittals.length ? '' : 'opacity-60'}>
                                            {proj.submittals.length} DRR
                                        </Badge>
                                        <Badge tint={proj.releases.length ? 'blue' : 'slate'} className={proj.releases.length ? '' : 'opacity-60'}>
                                            {proj.releases.length} releases
                                        </Badge>
                                    </span>
                                </ToggleRow>

                                {pOpen && (
                                    <div className="border-t border-gray-300 dark:border-slate-600">
                                        {/* DRR Submittals — lifecycle timeline */}
                                        <div className="py-3">
                                            <div className="pl-10 pr-4 pb-1.5 text-xs font-bold uppercase tracking-widest text-gray-600 dark:text-slate-300">
                                                DRR Submittals
                                            </div>
                                            <SubmittalTimeline submittals={proj.submittals} />
                                        </div>

                                        {/* Releases — expandable event rows */}
                                        <div className="py-3 border-t border-gray-300 dark:border-slate-600">
                                            <div className="pl-10 pr-4 pb-1.5 text-xs font-bold uppercase tracking-widest text-gray-600 dark:text-slate-300">
                                                Releases
                                            </div>
                                            {proj.releases.length === 0 && (
                                                <div className="px-8 py-3 text-sm text-gray-400 dark:text-slate-500 italic">
                                                    No release activity this month.
                                                </div>
                                            )}
                                            {proj.releases.map((r) => (
                                                <ReleaseRow
                                                    key={`${pKey}:rel:${r.job}-${r.release}`}
                                                    release={r}
                                                    onOpenHistory={setHistoryRelease}
                                                />
                                            ))}
                                        </div>
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>
            )}
            <ReleaseHistoryModal
                isOpen={!!historyRelease}
                release={historyRelease}
                onClose={() => setHistoryRelease(null)}
            />
        </div>
    );
}

export default InvoicingReport;
