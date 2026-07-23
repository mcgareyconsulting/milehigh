/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Admin Subs page — active releases assigned to subcontractor installers,
 *   grouped by installer, with a yes/no toggle for installer invoice paid.
 *   Distinct from Job Log "Invoiced" (MHMW customer billing).
 * exports:
 *   Subs: Page component (admin-gated).
 * imports_from: [react, ../utils/auth, ../services/subsApi]
 * imported_by: [App.jsx]
 * invariants:
 *   - Renders an access message (no fetch) unless the authenticated user is_admin.
 *   - Server enforces admin; optimistic toggle reverts on error.
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import { checkAuth } from '../utils/auth';
import { fetchSubsReleases, updateInstallerInvoicePaid } from '../services/subsApi';

const PAID_FILTERS = [
    { key: 'all', label: 'All', paid: undefined },
    { key: 'unpaid', label: 'Unpaid', paid: false },
    { key: 'paid', label: 'Paid', paid: true },
];

const fmtDate = (iso) => {
    if (!iso) return '—';
    const d = new Date(`${iso}T00:00:00`);
    return Number.isNaN(d.getTime())
        ? iso
        : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: '2-digit' });
};

function PaidToggle({ paid, busy, onChange }) {
    return (
        <div className="inline-flex rounded-md border border-gray-200 dark:border-slate-600 overflow-hidden text-xs font-medium">
            <button
                type="button"
                disabled={busy}
                onClick={() => onChange(false)}
                className={`px-2.5 py-1 transition-colors ${
                    !paid
                        ? 'bg-amber-100 text-amber-900 dark:bg-amber-500/25 dark:text-amber-100'
                        : 'bg-white text-gray-500 hover:bg-gray-50 dark:bg-slate-800 dark:text-slate-400 dark:hover:bg-slate-700'
                } ${busy ? 'opacity-60 cursor-wait' : ''}`}
            >
                No
            </button>
            <button
                type="button"
                disabled={busy}
                onClick={() => onChange(true)}
                className={`px-2.5 py-1 border-l border-gray-200 dark:border-slate-600 transition-colors ${
                    paid
                        ? 'bg-emerald-100 text-emerald-900 dark:bg-emerald-500/25 dark:text-emerald-100'
                        : 'bg-white text-gray-500 hover:bg-gray-50 dark:bg-slate-800 dark:text-slate-400 dark:hover:bg-slate-700'
                } ${busy ? 'opacity-60 cursor-wait' : ''}`}
            >
                Yes
            </button>
        </div>
    );
}

function groupByInstaller(releases) {
    const map = new Map();
    for (const r of releases) {
        const key = r.installer || 'Unassigned';
        if (!map.has(key)) map.set(key, []);
        map.get(key).push(r);
    }
    return [...map.entries()]; // already sorted by API
}

export default function Subs() {
    const [authorized, setAuthorized] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [releases, setReleases] = useState([]);
    const [installers, setInstallers] = useState([]);
    const [paidFilter, setPaidFilter] = useState('all');
    const [installerFilter, setInstallerFilter] = useState('');
    const [busyKey, setBusyKey] = useState(null);

    useEffect(() => {
        checkAuth().then((user) => setAuthorized(!!(user && user.is_admin)));
    }, []);

    const load = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const paidOpt = PAID_FILTERS.find((f) => f.key === paidFilter)?.paid;
            const data = await fetchSubsReleases({
                paid: paidOpt,
                installer: installerFilter || undefined,
            });
            setReleases(data.releases || []);
            setInstallers(data.installers || []);
        } catch (e) {
            setError(e?.response?.data?.error || e.message || 'Failed to load subs');
        } finally {
            setLoading(false);
        }
    }, [paidFilter, installerFilter]);

    useEffect(() => {
        if (authorized) load();
    }, [authorized, load]);

    const groups = useMemo(() => groupByInstaller(releases), [releases]);

    const totals = useMemo(() => {
        const unpaid = releases.filter((r) => !r.installer_invoice_paid).length;
        return { total: releases.length, unpaid, paid: releases.length - unpaid };
    }, [releases]);

    const rowKey = (r) => `${r.job}-${r.release}`;

    const handleToggle = async (row, nextPaid) => {
        if (boolEq(row.installer_invoice_paid, nextPaid)) return;
        const key = rowKey(row);
        setBusyKey(key);
        setError(null);
        const prev = row.installer_invoice_paid;
        setReleases((list) =>
            list.map((r) =>
                rowKey(r) === key ? { ...r, installer_invoice_paid: nextPaid } : r,
            ),
        );
        try {
            await updateInstallerInvoicePaid(row.job, row.release, nextPaid);
        } catch (e) {
            setReleases((list) =>
                list.map((r) =>
                    rowKey(r) === key ? { ...r, installer_invoice_paid: prev } : r,
                ),
            );
            setError(e?.response?.data?.error || e.message || 'Failed to update paid status');
        } finally {
            setBusyKey(null);
        }
    };

    if (authorized === null) {
        return <div className="p-6 text-gray-500 dark:text-slate-400">Loading…</div>;
    }
    if (!authorized) {
        return (
            <div className="p-6 text-gray-600 dark:text-slate-300">
                Subs is available to admins only.
            </div>
        );
    }

    return (
        <div className="flex-1 min-h-0 overflow-auto">
            <div className="max-w-6xl mx-auto px-4 sm:px-6 py-6">
                <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3 mb-5">
                    <div>
                        <h1 className="text-xl font-semibold text-gray-900 dark:text-slate-100">
                            Subs
                        </h1>
                        <p className="mt-1 text-sm text-gray-500 dark:text-slate-400">
                            Active releases by installer. Mark whether the subcontractor invoice is paid.
                        </p>
                    </div>
                    <div className="text-xs text-gray-500 dark:text-slate-400 tabular-nums">
                        {totals.total} release{totals.total === 1 ? '' : 's'}
                        {totals.total > 0 && (
                            <span className="ml-2">
                                · <span className="text-amber-700 dark:text-amber-300">{totals.unpaid} unpaid</span>
                                {' · '}
                                <span className="text-emerald-700 dark:text-emerald-300">{totals.paid} paid</span>
                            </span>
                        )}
                    </div>
                </div>

                {/* Filters */}
                <div className="flex flex-wrap items-center gap-2 mb-4">
                    <div className="inline-flex rounded-lg border border-gray-200 dark:border-slate-600 overflow-hidden text-sm">
                        {PAID_FILTERS.map((f) => (
                            <button
                                key={f.key}
                                type="button"
                                onClick={() => setPaidFilter(f.key)}
                                className={`px-3 py-1.5 ${
                                    paidFilter === f.key
                                        ? 'bg-accent-500 text-white'
                                        : 'bg-white dark:bg-slate-800 text-gray-600 dark:text-slate-300 hover:bg-gray-50 dark:hover:bg-slate-700'
                                } ${f.key !== 'all' ? 'border-l border-gray-200 dark:border-slate-600' : ''}`}
                            >
                                {f.label}
                            </button>
                        ))}
                    </div>

                    <select
                        value={installerFilter}
                        onChange={(e) => setInstallerFilter(e.target.value)}
                        className="text-sm rounded-lg border border-gray-200 dark:border-slate-600 bg-white dark:bg-slate-800 text-gray-700 dark:text-slate-200 px-3 py-1.5"
                    >
                        <option value="">All installers</option>
                        {installers.map((name) => (
                            <option key={name} value={name}>{name}</option>
                        ))}
                    </select>

                    <button
                        type="button"
                        onClick={load}
                        disabled={loading}
                        className="text-sm px-3 py-1.5 rounded-lg border border-gray-200 dark:border-slate-600 text-gray-600 dark:text-slate-300 hover:bg-gray-50 dark:hover:bg-slate-700 disabled:opacity-50"
                    >
                        Refresh
                    </button>
                </div>

                {error && (
                    <div className="mb-4 rounded-lg border border-red-200 dark:border-red-900/50 bg-red-50 dark:bg-red-950/40 text-red-800 dark:text-red-200 text-sm px-3 py-2">
                        {error}
                    </div>
                )}

                {loading && releases.length === 0 ? (
                    <div className="text-sm text-gray-500 dark:text-slate-400 py-8">Loading…</div>
                ) : releases.length === 0 ? (
                    <div className="rounded-lg border border-dashed border-gray-300 dark:border-slate-600 px-4 py-10 text-center text-sm text-gray-500 dark:text-slate-400">
                        No assigned installers on active releases.
                    </div>
                ) : (
                    <div className="space-y-6">
                        {groups.map(([installer, rows]) => {
                            const unpaidCount = rows.filter((r) => !r.installer_invoice_paid).length;
                            return (
                                <section key={installer}>
                                    <div className="sticky top-0 z-10 -mx-1 px-1 py-2 bg-[#f8fafc]/90 dark:bg-slate-900/90 backdrop-blur flex items-baseline justify-between gap-2 border-b border-gray-200 dark:border-slate-700 mb-2">
                                        <h2 className="text-sm font-semibold text-gray-900 dark:text-slate-100">
                                            {installer}
                                        </h2>
                                        <span className="text-xs text-gray-500 dark:text-slate-400 tabular-nums">
                                            {unpaidCount} unpaid · {rows.length} total
                                        </span>
                                    </div>

                                    <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800">
                                        <table className="w-full text-sm">
                                            <thead>
                                                <tr className="text-left text-xs uppercase tracking-wide text-gray-500 dark:text-slate-400 border-b border-gray-100 dark:border-slate-700">
                                                    <th className="px-3 py-2 font-medium">Job</th>
                                                    <th className="px-3 py-2 font-medium">Rel</th>
                                                    <th className="px-3 py-2 font-medium">Job name</th>
                                                    <th className="px-3 py-2 font-medium hidden md:table-cell">Description</th>
                                                    <th className="px-3 py-2 font-medium hidden sm:table-cell">Stage</th>
                                                    <th className="px-3 py-2 font-medium hidden lg:table-cell">Start install</th>
                                                    <th className="px-3 py-2 font-medium text-right">Invoice paid</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {rows.map((r) => {
                                                    const key = rowKey(r);
                                                    return (
                                                        <tr
                                                            key={key}
                                                            className="border-t border-gray-100 dark:border-slate-700/60 hover:bg-gray-50/80 dark:hover:bg-slate-700/30"
                                                        >
                                                            <td className="px-3 py-2 tabular-nums text-gray-900 dark:text-slate-100 font-medium">
                                                                {r.job}
                                                            </td>
                                                            <td className="px-3 py-2 tabular-nums text-gray-700 dark:text-slate-200">
                                                                {r.release}
                                                            </td>
                                                            <td className="px-3 py-2 text-gray-800 dark:text-slate-200 max-w-[12rem] truncate" title={r.job_name || ''}>
                                                                {r.job_name || '—'}
                                                            </td>
                                                            <td className="px-3 py-2 text-gray-600 dark:text-slate-300 hidden md:table-cell max-w-[14rem] truncate" title={r.description || ''}>
                                                                {r.description || '—'}
                                                            </td>
                                                            <td className="px-3 py-2 text-gray-600 dark:text-slate-300 hidden sm:table-cell">
                                                                {r.stage || '—'}
                                                            </td>
                                                            <td className="px-3 py-2 text-gray-600 dark:text-slate-300 hidden lg:table-cell tabular-nums">
                                                                {fmtDate(r.start_install)}
                                                            </td>
                                                            <td className="px-3 py-2 text-right">
                                                                <PaidToggle
                                                                    paid={!!r.installer_invoice_paid}
                                                                    busy={busyKey === key}
                                                                    onChange={(next) => handleToggle(r, next)}
                                                                />
                                                            </td>
                                                        </tr>
                                                    );
                                                })}
                                            </tbody>
                                        </table>
                                    </div>
                                </section>
                            );
                        })}
                    </div>
                )}
            </div>
        </div>
    );
}

function boolEq(a, b) {
    return !!a === !!b;
}
