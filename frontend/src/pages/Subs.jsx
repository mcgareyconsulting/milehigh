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

const fmtDate = (iso) => {
    if (!iso) return '—';
    const d = new Date(`${iso}T00:00:00`);
    return Number.isNaN(d.getTime())
        ? iso
        : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: '2-digit' });
};

function PaidToggle({ paid, busy, onChange }) {
    return (
        <div className="inline-flex rounded-md border border-hairline overflow-hidden text-xs font-medium">
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
                className={`px-2.5 py-1 border-l border-hairline transition-colors ${
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
                className={`w-12 px-1.5 py-1 text-sm tabular-nums text-center rounded-md border border-hairline bg-input-bg text-ink focus:outline-none focus:ring-1 focus:ring-accent-500 ${
                    busy ? 'opacity-60 cursor-wait' : ''
                }`}
            />
            <span className="text-xs text-ink-3">%</span>
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
            className={`w-full min-w-[7rem] max-w-[12rem] px-1.5 py-1 text-xs leading-snug rounded-md border border-hairline bg-input-bg text-ink resize-y focus:outline-none focus:ring-1 focus:ring-accent-500 ${
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
            // Server may normalize null
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
        return <div className="p-6 text-ink-3">Loading…</div>;
    }
    if (!authorized) {
        return (
            <div className="p-6 text-ink-2">
                Invoice Paid is available to admins only.
            </div>
        );
    }

    return (
        <div className="flex-1 min-h-0 overflow-auto">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 py-6">
                <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3 mb-5">
                    <div>
                        <h1 className="text-xl font-semibold text-ink">
                            Invoice Paid
                        </h1>
                        <p className="mt-1 text-sm text-ink-3">
                            Active releases by installer. Track progress, invoice numbers, and whether the subcontractor invoice is complete.
                        </p>
                    </div>
                    <div className="text-xs text-ink-3 tabular-nums notif-pod-reserve">
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
                    <div className="inline-flex rounded-lg border border-hairline overflow-hidden text-sm">
                        {PAID_FILTERS.map((f) => (
                            <button
                                key={f.key}
                                type="button"
                                onClick={() => setPaidFilter(f.key)}
                                className={`px-3 py-1.5 ${
                                    paidFilter === f.key
                                        ? 'bg-accent-500 text-white'
                                        : 'bg-surface text-ink-2 hover:bg-surface-2'
                                } ${f.key !== 'all' ? 'border-l border-hairline' : ''}`}
                            >
                                {f.label}
                            </button>
                        ))}
                    </div>

                    <select
                        value={installerFilter}
                        onChange={(e) => setInstallerFilter(e.target.value)}
                        className="text-sm rounded-lg border border-hairline bg-input-bg text-ink-2 px-3 py-1.5"
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
                        className="text-sm px-3 py-1.5 rounded-lg border border-hairline text-ink-2 hover:bg-surface-2 disabled:opacity-50"
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
                    <div className="text-sm text-ink-3 py-8">Loading…</div>
                ) : releases.length === 0 ? (
                    <div className="rounded-lg border border-dashed border-hairline-strong px-4 py-10 text-center text-sm text-ink-3">
                        No assigned installers on active releases.
                    </div>
                ) : (
                    <div className="space-y-6">
                        {groups.map(([installer, rows]) => {
                            const unpaidCount = rows.filter((r) => !r.installer_invoice_paid).length;
                            return (
                                <section key={installer}>
                                    <div className="sticky top-0 z-10 -mx-1 px-1 py-2 bg-canvas/90 backdrop-blur flex items-baseline justify-between gap-2 border-b border-hairline mb-2">
                                        <h2 className="text-sm font-semibold text-ink">
                                            {installer}
                                        </h2>
                                        <span className="text-xs text-ink-3 tabular-nums">
                                            {unpaidCount} unpaid · {rows.length} total
                                        </span>
                                    </div>

                                    <div className="overflow-x-auto rounded-lg border border-hairline bg-surface">
                                        <table className="w-full text-sm">
                                            <thead>
                                                <tr className="text-left text-xs uppercase tracking-wide text-ink-3 border-b border-hairline">
                                                    <th className="px-3 py-2 font-medium">Job</th>
                                                    <th className="px-3 py-2 font-medium">Rel</th>
                                                    <th className="px-3 py-2 font-medium">Job name</th>
                                                    <th className="px-3 py-2 font-medium hidden md:table-cell">Description</th>
                                                    <th className="px-3 py-2 font-medium hidden sm:table-cell">Stage</th>
                                                    <th className="px-3 py-2 font-medium hidden lg:table-cell">Start install</th>
                                                    <th className="px-3 py-2 font-medium whitespace-nowrap">Progress</th>
                                                    <th className="px-3 py-2 font-medium whitespace-nowrap">Invoice #</th>
                                                    <th className="px-3 py-2 font-medium text-right whitespace-nowrap">Invoiced complete</th>
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
                                                            <td className="px-3 py-2 tabular-nums text-ink font-medium align-top">
                                                                {r.job}
                                                            </td>
                                                            <td className="px-3 py-2 tabular-nums text-ink-2 align-top">
                                                                {r.release}
                                                            </td>
                                                            <td className="px-3 py-2 text-ink-2 max-w-[12rem] truncate align-top" title={r.job_name || ''}>
                                                                {r.job_name || '—'}
                                                            </td>
                                                            <td className="px-3 py-2 text-ink-2 hidden md:table-cell max-w-[14rem] truncate align-top" title={r.description || ''}>
                                                                {r.description || '—'}
                                                            </td>
                                                            <td className="px-3 py-2 text-ink-2 hidden sm:table-cell align-top">
                                                                {r.stage || '—'}
                                                            </td>
                                                            <td className="px-3 py-2 text-ink-2 hidden lg:table-cell tabular-nums align-top">
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
