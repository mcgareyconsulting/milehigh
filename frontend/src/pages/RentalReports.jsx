/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Admin Sunbelt rental report — the weekly Equipment-on-Rent feed reconciled to our jobs,
 *   shown as a dense full-width table with our project #/name primary, color-coded date/cost
 *   discrepancy flags, accrued-cost estimate, snapshot history, and week-over-week change accents.
 * exports:
 *   RentalReports: Page component (admin-gated).
 * imports_from: [react, ../services/sunbeltApi, ../utils/auth]
 * imported_by: [frontend/src/App.jsx]
 * invariants:
 *   - Renders an access message (no fetch) unless the authenticated user is_admin.
 *   - Backend computes discrepancy flags relative to today; the UI only colors them.
 *   - matched_job_number/name are ours; match_method='address' marks a PO that only matched by site.
 */
import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { sunbeltApi } from '../services/sunbeltApi';
import { checkAuth } from '../utils/auth';
import Stat from '../components/shared/Stat';

// Week-over-week change -> left-border accent.
const CHANGE_META = {
    new: { border: 'border-l-emerald-400 dark:border-l-emerald-500' },
    changed: { border: 'border-l-blue-400 dark:border-l-blue-500' },
    unchanged: { border: 'border-l-transparent' },
};

const money0 = (v) =>
    v == null ? '—' : new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(v);

// Parse 'YYYY-MM-DD' without timezone drift.
function parseISO(iso) {
    if (!iso) return null;
    const m = String(iso).match(/^(\d{4})-(\d{2})-(\d{2})/);
    return m ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : null;
}
// Dense numeric date: 6/2/26.
function shortDate(iso) {
    const d = parseISO(iso);
    return d ? `${d.getMonth() + 1}/${d.getDate()}/${String(d.getFullYear()).slice(2)}` : '—';
}
function daysBetween(iso, today) {
    const d = parseISO(iso);
    return d ? Math.round((today - d) / 86400000) : null;
}
// Rough accrued cost since the unit was rented: (weeks on rent) * week rate.
function accruedCost(r, today) {
    if (r.week_rate == null || !r.date_rented) return null;
    const days = daysBetween(r.date_rented, today);
    if (days == null || days <= 0) return 0;
    return (days / 7) * r.week_rate;
}

function RentalRow({ r, today }) {
    const unmatched = r.match_method === 'unmatched';
    const byAddress = r.match_method === 'address';
    const change = CHANGE_META[r.change] || CHANGE_META.unchanged;
    const accrued = accruedCost(r, today);
    const onRent = daysBetween(r.date_rented, today);
    const overdueDays = r.est_return_date ? daysBetween(r.est_return_date, today) : null;

    const cell = 'px-2 py-2 whitespace-nowrap';
    return (
        <tr className={`border-b border-gray-100 dark:border-slate-700/60 border-l-2 ${change.border} ${unmatched ? 'bg-slate-50/70 dark:bg-slate-800/40' : 'hover:bg-gray-50 dark:hover:bg-slate-800/40'}`}>
            <td className={`${cell} font-semibold text-gray-900 dark:text-slate-100`}>
                {r.matched_job_number ?? <span className="text-gray-400">—</span>}
                {byAddress && <span title="Matched by site address (PO mismatch)" className="ml-0.5 text-amber-500 cursor-help">≈</span>}
            </td>
            <td className={`px-2 py-2 max-w-[16rem] truncate ${r.matched_project_name ? 'text-gray-800 dark:text-slate-200' : 'text-gray-400 dark:text-slate-500 italic'}`}
                title={r.matched_project_name || r.sunbelt_job_label || ''}>
                {r.matched_project_name || r.sunbelt_job_label || 'Unmatched'}
            </td>
            <td className={`px-2 py-2 max-w-[18rem] truncate text-gray-700 dark:text-slate-300`} title={r.equipment_type || ''}>
                {r.equipment_type || '—'}
            </td>
            <td className={`${cell} text-gray-500 dark:text-slate-400 text-xs`}>{[r.make, r.model].filter(Boolean).join(' ') || '—'}</td>
            <td className={`${cell} text-gray-400 dark:text-slate-500 text-xs`}>{r.equipment_number || '—'}</td>
            <td className={`${cell} text-center text-gray-600 dark:text-slate-400`}>{r.quantity ?? 1}</td>
            <td className={`${cell} text-right tabular-nums text-gray-700 dark:text-slate-300`}>{money0(r.week_rate)}</td>
            <td className={`${cell} text-right tabular-nums font-medium text-gray-800 dark:text-slate-200`}>{money0(accrued)}</td>
            <td className={`${cell} text-right tabular-nums text-gray-500 dark:text-slate-400`}>{onRent != null ? `${onRent}d` : '—'}</td>
            <td className={`${cell} text-gray-600 dark:text-slate-400`}>{shortDate(r.date_rented)}</td>
            <td className={`${cell} ${overdueDays != null && overdueDays > 0 ? 'text-red-600 dark:text-red-400 font-medium' : 'text-gray-600 dark:text-slate-400'}`}>
                {shortDate(r.est_return_date)}
            </td>
            <td className={`${cell} text-gray-500 dark:text-slate-400`}>{shortDate(r.billed_through)}</td>
        </tr>
    );
}

function RentalReports() {
    const [authorized, setAuthorized] = useState(null);
    const [report, setReport] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [selectedSnapshot, setSelectedSnapshot] = useState('');
    const [uploading, setUploading] = useState(false);
    const [uploadMsg, setUploadMsg] = useState(null);
    const [query, setQuery] = useState('');
    const [flaggedOnly, setFlaggedOnly] = useState(false);
    const fileInputRef = useRef(null);
    const today = useMemo(() => new Date(), []);

    useEffect(() => {
        checkAuth().then((user) => setAuthorized(!!user?.is_admin));
    }, []);

    const fetchReport = useCallback(async (snapshotId) => {
        setLoading(true);
        setError(null);
        try {
            const data = await sunbeltApi.fetchReport(snapshotId || undefined);
            setReport(data);
        } catch (err) {
            setError(err.message);
            setReport(null);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        if (authorized) fetchReport(selectedSnapshot);
    }, [authorized, selectedSnapshot, fetchReport]);

    const onUpload = useCallback(async (e) => {
        const file = e.target.files?.[0];
        if (!file) return;
        setUploading(true);
        setUploadMsg(null);
        setError(null);
        try {
            const result = await sunbeltApi.uploadCsv(file);
            setUploadMsg(`Imported ${result.snapshot?.row_count ?? 0} rentals.`);
            setSelectedSnapshot('');
            await fetchReport('');
        } catch (err) {
            setError(err.message);
        } finally {
            setUploading(false);
            if (fileInputRef.current) fileInputRef.current.value = '';
        }
    }, [fetchReport]);

    const rentals = useMemo(() => report?.rentals || [], [report]);
    const totals = report?.totals || {};
    const snapshots = report?.snapshots || [];
    const returned = report?.returned || [];

    const flagCounts = useMemo(() => {
        const c = { overdue: 0, on_finished_job: 0, cost_outlier: 0 };
        for (const r of rentals) for (const d of (r.discrepancies || [])) if (c[d.type] != null) c[d.type]++;
        return c;
    }, [rentals]);

    const accruedTotal = useMemo(
        () => rentals.reduce((sum, r) => sum + (accruedCost(r, today) || 0), 0),
        [rentals, today],
    );

    const visible = useMemo(() => {
        const q = query.trim().toLowerCase();
        return rentals.filter((r) => {
            if (flaggedOnly && !(r.discrepancies || []).length) return false;
            if (!q) return true;
            return [r.matched_project_name, r.sunbelt_job_label, r.matched_job_number, r.po_number, r.equipment_type, r.equipment_number, r.make, r.model]
                .some((v) => String(v ?? '').toLowerCase().includes(q));
        });
    }, [rentals, query, flaggedOnly]);

    if (authorized === null) {
        return <div className="flex-1 flex items-center justify-center text-gray-600 dark:text-slate-400">Loading…</div>;
    }
    if (!authorized) {
        return (
            <div className="flex-1 flex items-center justify-center p-6 text-center">
                <div className="text-gray-600 dark:text-slate-400">You don’t have access to rental reports.</div>
            </div>
        );
    }

    const selectClass = 'px-2.5 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-gray-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-accent-400/60';
    const th = 'px-2 py-1.5 font-semibold text-left whitespace-nowrap';

    return (
        <div className="flex-1 w-full overflow-auto px-3 lg:px-5 py-3">
            {/* Header */}
            <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
                <div>
                    <h1 className="text-xl font-bold text-gray-900 dark:text-slate-100">Sunbelt Rentals</h1>
                    <p className="text-xs text-gray-500 dark:text-slate-400">
                        Equipment on rent, reconciled to our jobs.
                        {report?.snapshot && <> · Report dated <span className="font-medium">{shortDate(report.snapshot.snapshot_date)}</span></>}
                        {report?.snapshot?.created_by && <> · by {report.snapshot.created_by}</>}
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    {snapshots.length > 0 && (
                        <select className={selectClass} value={selectedSnapshot} onChange={(e) => setSelectedSnapshot(e.target.value)}>
                            <option value="">Latest</option>
                            {snapshots.map((s) => (
                                <option key={s.id} value={s.id}>{shortDate(s.snapshot_date)} ({s.row_count})</option>
                            ))}
                        </select>
                    )}
                    <label className={`inline-flex items-center gap-2 px-3 py-1.5 text-sm font-medium rounded-lg cursor-pointer text-white bg-accent-500 hover:bg-accent-600 ${uploading ? 'opacity-70 cursor-wait' : ''}`}>
                        {uploading ? 'Uploading…' : 'Upload CSV'}
                        <input ref={fileInputRef} type="file" accept=".csv,text/csv" className="hidden" disabled={uploading} onChange={onUpload} />
                    </label>
                </div>
            </div>

            {/* Summary stats */}
            <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-7 gap-2 mb-3">
                <Stat label="Rentals" value={totals.rental_count ?? 0} />
                <Stat label="Overdue" value={flagCounts.overdue} tone={flagCounts.overdue ? 'red' : 'slate'} />
                <Stat label="Job done" value={flagCounts.on_finished_job} tone={flagCounts.on_finished_job ? 'amber' : 'slate'} />
                <Stat label="Cost flags" value={flagCounts.cost_outlier} tone={flagCounts.cost_outlier ? 'orange' : 'slate'} />
                <Stat label="Weekly cost" value={money0(totals.weekly_total)} />
                <Stat label="Accrued (est)" value={money0(accruedTotal)} />
                <Stat label="Returned" value={returned.length} tone="slate" />
            </div>

            {/* Toolbar */}
            <div className="flex flex-wrap items-center gap-2 mb-2">
                <input
                    type="text"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Filter by job, project, equipment…"
                    className={`${selectClass} w-64`}
                />
                <label className="inline-flex items-center gap-1.5 text-sm text-gray-600 dark:text-slate-300 cursor-pointer select-none">
                    <input type="checkbox" checked={flaggedOnly} onChange={(e) => setFlaggedOnly(e.target.checked)} className="rounded border-gray-300 dark:border-slate-600" />
                    Flagged only
                </label>
                <span className="text-xs text-gray-400 dark:text-slate-500">{visible.length} of {rentals.length} shown</span>
                {uploadMsg && <span className="text-xs text-emerald-600 dark:text-emerald-400 ml-auto">{uploadMsg}</span>}
                {error && <span className="text-xs text-red-600 dark:text-red-400 ml-auto">{error}</span>}
            </div>

            {/* Table */}
            {loading ? (
                <div className="py-12 text-center text-gray-500 dark:text-slate-400">Loading…</div>
            ) : rentals.length === 0 ? (
                <div className="py-12 text-center text-gray-500 dark:text-slate-400">No rentals yet. Upload a weekly Sunbelt CSV to get started.</div>
            ) : (
                <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-slate-700">
                    <table className="w-full text-xs">
                        <thead className="bg-gray-50 dark:bg-slate-800 text-gray-500 dark:text-slate-400 sticky top-0 z-10">
                            <tr>
                                <th className={th}>Job #</th>
                                <th className={th}>Project</th>
                                <th className={th}>Equipment</th>
                                <th className={th}>Make/Model</th>
                                <th className={th}>Unit #</th>
                                <th className={`${th} text-center`}>Qty</th>
                                <th className={`${th} text-right`}>Wk rate</th>
                                <th className={`${th} text-right`}>Accrued</th>
                                <th className={`${th} text-right`}>On rent</th>
                                <th className={th}>Rented</th>
                                <th className={th}>Est. ret.</th>
                                <th className={th}>Billed thru</th>
                            </tr>
                        </thead>
                        <tbody className="bg-white dark:bg-slate-900">
                            {visible.map((r) => <RentalRow key={r.id} r={r} today={today} />)}
                        </tbody>
                    </table>
                </div>
            )}

            {/* Returned since previous snapshot */}
            {returned.length > 0 && (
                <div className="mt-4">
                    <h2 className="text-xs font-semibold text-gray-700 dark:text-slate-300 mb-1.5">Returned since previous report ({returned.length})</h2>
                    <div className="flex flex-wrap gap-1.5">
                        {returned.map((r, i) => (
                            <span key={i} className="inline-block px-2 py-0.5 rounded text-[11px] bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300">
                                {(r.matched_project_name || r.matched_job_number || 'Unmatched')} · {r.equipment_type}
                            </span>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}

export default RentalReports;
