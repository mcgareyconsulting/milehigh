/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Admin "Invoice Paid" tab under the Subs shell — active releases assigned
 *   to subcontractor installers, grouped by installer. Tracks progress %, invoice
 *   number(s), and invoiced-complete (yes/no). Distinct from top-level customer
 *   "Invoicing" and from Job Log "Invoiced".
 * exports:
 *   Subs: Page component (admin-gated).
 * imports_from: [react, ../utils/auth, ../services/subsApi]
 * imported_by: [App.jsx via SubsLayout at /subs/invoice-paid]
 * invariants:
 *   - Renders an access message (no fetch) unless the authenticated user is_admin.
 *   - Server enforces admin; optimistic edits revert on error.
 *   - Styling matches Subs sibling pages (SubcontractorAdmin / T&M token shell).
 */
import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { checkAuth } from '../utils/auth';
import {
    fetchSubsReleases,
    updateInstallerInvoicePaid,
    updateInstallerInvoiceProgress,
    updateInstallerInvoiceNumbers,
} from '../services/subsApi';

const PAID_FILTERS = [
    { key: 'all', label: 'All', paid: undefined },
    { key: 'unpaid', label: 'Unpaid', paid: false },
    { key: 'paid', label: 'Paid', paid: true },
];

const inputClass =
    'rounded border border-hairline-strong bg-input-bg text-ink focus:outline-none focus:ring-1 focus:ring-accent-500';

const fmtDate = (iso) => {
    if (!iso) return '—';
    const d = new Date(`${iso}T00:00:00`);
    return Number.isNaN(d.getTime())
        ? iso
        : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: '2-digit' });
};

function PaidToggle({ paid, busy, onChange }) {
    return (
        <div className="inline-flex rounded border border-hairline-strong overflow-hidden text-xs font-medium">
            <button
                type="button"
                disabled={busy}
                onClick={() => onChange(false)}
                className={`px-2.5 py-1 transition-colors ${
                    !paid
                        ? 'bg-amber-100 text-amber-900 dark:bg-amber-500/25 dark:text-amber-100'
                        : 'bg-surface text-ink-3 hover:bg-surface-2'
                } ${busy ? 'opacity-60 cursor-wait' : ''}`}
            >
                No
            </button>
            <button
                type="button"
                disabled={busy}
                onClick={() => onChange(true)}
                className={`px-2.5 py-1 border-l border-hairline-strong transition-colors ${
                    paid
                        ? 'bg-emerald-100 text-emerald-900 dark:bg-emerald-500/25 dark:text-emerald-100'
                        : 'bg-surface text-ink-3 hover:bg-surface-2'
                } ${busy ? 'opacity-60 cursor-wait' : ''}`}
            >
                Yes
            </button>
        </div>
    );
}

/** Progress % cell — commits on blur / Enter. */
function ProgressInput({ value, busy, onCommit }) {
    const [draft, setDraft] = useState(value == null ? '' : String(value));
    const lastProp = useRef(value);

    useEffect(() => {
        if (lastProp.current !== value) {
            lastProp.current = value;
            setDraft(value == null ? '' : String(value));
        }
    }, [value]);

    const commit = () => {
        const trimmed = draft.trim();
        if (trimmed === '') {
            if (value != null) onCommit(null);
            else setDraft('');
            return;
        }
        const n = Number(trimmed);
        if (!Number.isInteger(n) || n < 0 || n > 100) {
            setDraft(value == null ? '' : String(value));
            return;
        }
        if (n !== value) onCommit(n);
        else setDraft(String(n));
    };

    return (
        <div className="inline-flex items-center gap-0.5">
            <input
                type="text"
                inputMode="numeric"
                value={draft}
                disabled={busy}
                onChange={(e) => setDraft(e.target.value)}
                onBlur={commit}
                onKeyDown={(e) => {
                    if (e.key === 'Enter') e.currentTarget.blur();
                    if (e.key === 'Escape') {
                        setDraft(value == null ? '' : String(value));
                        e.currentTarget.blur();
                    }
                }}
                placeholder="—"
                aria-label="Progress percent"
                className={`w-11 px-1 py-0.5 text-jl font-mono tabular-nums text-center ${inputClass} ${
                    busy ? 'opacity-60 cursor-wait' : ''
                }`}
            />
            <span className="text-jl-3 text-ink-3">%</span>
        </div>
    );
}

/** Multi-line invoice numbers — commits on blur. */
function InvoiceNumbersInput({ value, busy, onCommit }) {
    const [draft, setDraft] = useState(value || '');
    const lastProp = useRef(value);

    useEffect(() => {
        if (lastProp.current !== value) {
            lastProp.current = value;
            setDraft(value || '');
        }
    }, [value]);

    const commit = () => {
        const prev = (value || '').trim();
        const next = draft.trim();
        if (next === prev) {
            setDraft(value || '');
            return;
        }
        onCommit(next);
    };

    return (
        <textarea
            value={draft}
            disabled={busy}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={commit}
            onKeyDown={(e) => {
                if (e.key === 'Escape') {
                    setDraft(value || '');
                    e.currentTarget.blur();
                }
            }}
            rows={2}
            placeholder="Invoice #"
            aria-label="Invoice numbers"
            className={`w-full min-w-[6.5rem] max-w-[11rem] px-1.5 py-0.5 text-jl font-mono leading-snug resize-y ${inputClass} ${
                busy ? 'opacity-60 cursor-wait' : ''
            }`}
        />
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

    const patchRow = (key, partial) => {
        setReleases((list) =>
            list.map((r) => (rowKey(r) === key ? { ...r, ...partial } : r)),
        );
    };

    const handleToggle = async (row, nextPaid) => {
        if (boolEq(row.installer_invoice_paid, nextPaid)) return;
        const key = rowKey(row);
        setBusyKey(`${key}:paid`);
        setError(null);
        const prev = row.installer_invoice_paid;
        patchRow(key, { installer_invoice_paid: nextPaid });
        try {
            await updateInstallerInvoicePaid(row.job, row.release, nextPaid);
        } catch (e) {
            patchRow(key, { installer_invoice_paid: prev });
            setError(e?.response?.data?.error || e.message || 'Failed to update paid status');
        } finally {
            setBusyKey(null);
        }
    };

    const handleProgress = async (row, nextProgress) => {
        const key = rowKey(row);
        const prev = row.installer_invoice_progress ?? null;
        if (prev === nextProgress) return;
        setBusyKey(`${key}:progress`);
        setError(null);
        patchRow(key, { installer_invoice_progress: nextProgress });
        try {
            const res = await updateInstallerInvoiceProgress(row.job, row.release, nextProgress);
            if (res && 'installer_invoice_progress' in res) {
                patchRow(key, { installer_invoice_progress: res.installer_invoice_progress });
            }
        } catch (e) {
            patchRow(key, { installer_invoice_progress: prev });
            setError(e?.response?.data?.error || e.message || 'Failed to update progress');
        } finally {
            setBusyKey(null);
        }
    };

    const handleInvoiceNumbers = async (row, nextNumbers) => {
        const key = rowKey(row);
        const prev = row.installer_invoice_numbers || '';
        const next = nextNumbers || '';
        if (prev.trim() === next.trim()) return;
        setBusyKey(`${key}:numbers`);
        setError(null);
        patchRow(key, { installer_invoice_numbers: next });
        try {
            const res = await updateInstallerInvoiceNumbers(row.job, row.release, next);
            if (res && 'installer_invoice_numbers' in res) {
                patchRow(key, { installer_invoice_numbers: res.installer_invoice_numbers || '' });
            }
        } catch (e) {
            patchRow(key, { installer_invoice_numbers: prev });
            setError(e?.response?.data?.error || e.message || 'Failed to update invoice numbers');
        } finally {
            setBusyKey(null);
        }
    };

    if (authorized === null) {
        return (
            <div className="w-full min-h-[calc(100vh_-_var(--app-chrome-h))] bg-canvas flex items-center justify-center text-ink-3">
                Loading…
            </div>
        );
    }
    if (!authorized) {
        return (
            <div className="w-full min-h-[calc(100vh_-_var(--app-chrome-h))] bg-canvas flex items-center justify-center p-6 text-center text-ink-3">
                Invoice Paid is available to admins only.
            </div>
        );
    }

    return (
        <div className="w-full min-h-[calc(100vh_-_var(--app-chrome-h))] bg-canvas">
            <div className="flex-1 p-4 md:p-6 max-w-[1400px] mx-auto w-full">
                {/* Header — matches SubcontractorAdmin / T&M */}
                <div className="flex items-start sm:items-center justify-between gap-3 mb-4 flex-wrap">
                    <div className="min-w-0">
                        <h1 className="text-xl font-bold text-ink">Invoice Paid</h1>
                        <p className="mt-0.5 text-sm text-ink-3">
                            Active releases by installer. Progress, invoice numbers, and complete status.
                        </p>
                    </div>
                    <div className="text-xs text-ink-3 font-mono tabular-nums notif-pod-reserve shrink-0">
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

                {/* Filters — pill buttons like T&M status tabs */}
                <div className="flex items-center gap-1.5 flex-wrap mb-4">
                    {PAID_FILTERS.map((f) => (
                        <button
                            key={f.key}
                            type="button"
                            onClick={() => setPaidFilter(f.key)}
                            className={`px-3 py-1.5 text-sm rounded-lg border transition-colors ${
                                paidFilter === f.key
                                    ? 'bg-accent-500 border-accent-500 text-white'
                                    : 'bg-surface border-hairline text-ink-2 hover:bg-surface-2'
                            }`}
                        >
                            {f.label}
                        </button>
                    ))}

                    <select
                        value={installerFilter}
                        onChange={(e) => setInstallerFilter(e.target.value)}
                        className="text-sm rounded-lg border border-hairline bg-surface text-ink-2 px-3 py-1.5"
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
                        className="text-sm px-3 py-1.5 rounded-lg border border-hairline-strong text-ink-2 hover:bg-surface-2 disabled:opacity-50"
                    >
                        Refresh
                    </button>
                </div>

                {error && (
                    <div className="mb-3 px-3 py-2 rounded-lg bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-300 text-sm">
                        {error}
                    </div>
                )}

                {loading && releases.length === 0 ? (
                    <div className="flex items-center justify-center py-16">
                        <span className="text-ink-3">Loading…</span>
                    </div>
                ) : releases.length === 0 ? (
                    <div className="rounded-xl border border-dashed border-hairline-strong p-12 text-center text-sm text-ink-3">
                        No assigned installers on active releases.
                    </div>
                ) : (
                    <div className="space-y-5">
                        {groups.map(([installer, rows]) => {
                            const unpaidCount = rows.filter((r) => !r.installer_invoice_paid).length;
                            return (
                                <section key={installer}>
                                    <div className="flex items-baseline justify-between gap-2 mb-1.5 px-0.5">
                                        <h2 className="text-sm font-bold text-ink">
                                            {installer}
                                        </h2>
                                        <span className="text-xs text-ink-3 font-mono tabular-nums">
                                            {unpaidCount} unpaid · {rows.length} total
                                        </span>
                                    </div>

                                    <div className="overflow-x-auto rounded-xl border border-hairline bg-surface">
                                        <table className="min-w-full text-sm">
                                            <thead className="bg-head-bg">
                                                <tr>
                                                    <th className="px-3 py-2 text-left font-semibold text-ink-3">Job</th>
                                                    <th className="px-3 py-2 text-left font-semibold text-ink-3">Rel</th>
                                                    <th className="px-3 py-2 text-left font-semibold text-ink-3">Job name</th>
                                                    <th className="px-3 py-2 text-left font-semibold text-ink-3 hidden md:table-cell">Description</th>
                                                    <th className="px-3 py-2 text-left font-semibold text-ink-3 hidden sm:table-cell">Stage</th>
                                                    <th className="px-3 py-2 text-left font-semibold text-ink-3 hidden lg:table-cell whitespace-nowrap">Start install</th>
                                                    <th className="px-3 py-2 text-left font-semibold text-ink-3 whitespace-nowrap">Progress</th>
                                                    <th className="px-3 py-2 text-left font-semibold text-ink-3 whitespace-nowrap">Invoice #</th>
                                                    <th className="px-3 py-2 text-right font-semibold text-ink-3 whitespace-nowrap">Invoiced complete</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {rows.map((r) => {
                                                    const key = rowKey(r);
                                                    const busyPaid = busyKey === `${key}:paid`;
                                                    const busyProgress = busyKey === `${key}:progress`;
                                                    const busyNumbers = busyKey === `${key}:numbers`;
                                                    return (
                                                        <tr
                                                            key={key}
                                                            className="border-t border-hairline hover:bg-surface-2"
                                                        >
                                                            <td className="px-3 py-2 font-mono tabular-nums text-ink align-top">
                                                                {r.job}
                                                            </td>
                                                            <td className="px-3 py-2 font-mono tabular-nums text-ink-2 align-top">
                                                                {r.release}
                                                            </td>
                                                            <td className="px-3 py-2 text-ink max-w-[12rem] truncate align-top" title={r.job_name || ''}>
                                                                {r.job_name || '—'}
                                                            </td>
                                                            <td className="px-3 py-2 text-ink-2 hidden md:table-cell max-w-[14rem] truncate align-top" title={r.description || ''}>
                                                                {r.description || '—'}
                                                            </td>
                                                            <td className="px-3 py-2 text-ink-2 hidden sm:table-cell align-top">
                                                                {r.stage || '—'}
                                                            </td>
                                                            <td className="px-3 py-2 text-ink-2 hidden lg:table-cell font-mono tabular-nums align-top whitespace-nowrap">
                                                                {fmtDate(r.start_install)}
                                                            </td>
                                                            <td className="px-3 py-2 align-top">
                                                                <ProgressInput
                                                                    value={r.installer_invoice_progress}
                                                                    busy={busyProgress}
                                                                    onCommit={(n) => handleProgress(r, n)}
                                                                />
                                                            </td>
                                                            <td className="px-3 py-2 align-top">
                                                                <InvoiceNumbersInput
                                                                    value={r.installer_invoice_numbers}
                                                                    busy={busyNumbers}
                                                                    onCommit={(v) => handleInvoiceNumbers(r, v)}
                                                                />
                                                            </td>
                                                            <td className="px-3 py-2 text-right align-top">
                                                                <PaidToggle
                                                                    paid={!!r.installer_invoice_paid}
                                                                    busy={busyPaid}
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
