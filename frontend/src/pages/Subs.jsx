/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Admin "Invoice Paid" tab under the Subs shell — active releases assigned
 *   to subcontractor installers, grouped by installer. Tracks progress %, invoice
 *   number(s), and invoiced-complete (yes/no). Distinct from top-level customer
 *   "Invoicing" and from Job Log "Invoiced".
 * exports:
 *   Subs: Page component (admin-gated).
 * imports_from: [react, ../utils/auth, ../utils/formatters, ../services/subsApi,
 *   ../components/ReleaseHubModal, ../components/JobDetailsBody]
 * imported_by: [App.jsx via SubsLayout at /subs/invoice-paid]
 * invariants:
 *   - Renders an access message (no fetch) unless the authenticated user is_admin.
 *   - Server enforces admin; optimistic edits revert on error.
 *   - Styling matches Subs sibling pages (SubcontractorAdmin / T&M token shell).
 *   - Job name / Description open the same ReleaseHubModal the Job Log opens; the
 *     API row carries the raw job-log fields that modal reads.
 *   - "Install Prog" mirrors the Job Log (job_comp) and is READ-ONLY here; the
 *     editable "Progress" column is the separate installer_invoice_progress field.
 *   - "Install Hrs" mirrors the Job Log (install_hrs) and is READ-ONLY here.
 *   - Budget = Install Hrs x $55; Est. Billable = Install Prog % x Budget. Both are
 *     derived on render (never stored), and blank rather than $0 when an input is
 *     missing — an unknown progress is not the same claim as zero work done.
 */
import { Fragment, useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { checkAuth } from '../utils/auth';
import { ReleaseHubModal } from '../components/ReleaseHubModal';
import { formatInstallProg } from '../components/JobDetailsBody';
import { formatCellValue } from '../utils/formatters';
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

/** Sub install rate. Budget = Install Hrs x this. */
const INSTALL_RATE_PER_HOUR = 55;

/** Install Hrs -> budget dollars. Null when hours are missing/non-numeric. */
function installBudget(installHrs) {
    const n = Number(installHrs);
    if (installHrs == null || installHrs === '' || !Number.isFinite(n)) return null;
    return n * INSTALL_RATE_PER_HOUR;
}

/**
 * Job Log install progress (job_comp) as a 0–1 fraction for billing math.
 *   "90" / "90%" / "90.5%" -> 0.9 / 0.9 / 0.905
 *   "X"                    -> 1 (the Job Log's complete marker)
 *   blank / "O" / junk     -> null (unknown, not zero — caller renders an em dash)
 *
 * The percent sign is part of the stored value on real rows (job_comp is free
 * text typed on the Job Log, e.g. "90%"), so it has to be tolerated, not just
 * bare digits. Over-100 entries clamp to 100% — a release cannot bill more than
 * its budget on progress alone.
 */
function installProgFraction(jobComp) {
    if (jobComp == null || jobComp === false) return null;
    const s = String(jobComp).trim();
    if (!s || s.toUpperCase() === 'O') return null;
    if (s.toUpperCase() === 'X') return 1;
    const m = /^(\d+(?:\.\d+)?)\s*%?$/.exec(s);
    if (!m) return null;
    return Math.min(Number(m[1]) / 100, 1);
}

/** Budget earned so far: install progress % x budget. Null if either is unknown. */
function estimatedBillable(jobComp, installHrs) {
    const budget = installBudget(installHrs);
    const fraction = installProgFraction(jobComp);
    if (budget == null || fraction == null) return null;
    return budget * fraction;
}

const fmtUsd = (amount) =>
    amount == null
        ? '—'
        : amount.toLocaleString('en-US', {
              style: 'currency',
              currency: 'USD',
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
          });

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
            className={`w-full max-w-[11rem] mx-auto block px-1.5 py-0.5 text-jl font-mono leading-snug text-center resize-y ${inputClass} ${
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
    const [searchInput, setSearchInput] = useState('');
    const [searchQ, setSearchQ] = useState('');
    const [busyKey, setBusyKey] = useState(null);
    // Release hub modal — same component the Job Log opens from its Description
    // cell. Held by row key (not the object) so the open modal tracks list edits.
    const [hubKey, setHubKey] = useState(null);

    useEffect(() => {
        checkAuth().then((user) => setAuthorized(!!(user && user.is_admin)));
    }, []);

    // Debounce free-text search so we don't hit the API on every keystroke.
    useEffect(() => {
        const t = setTimeout(() => setSearchQ(searchInput.trim()), 300);
        return () => clearTimeout(t);
    }, [searchInput]);

    const load = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const paidOpt = PAID_FILTERS.find((f) => f.key === paidFilter)?.paid;
            const data = await fetchSubsReleases({
                paid: paidOpt,
                installer: installerFilter || undefined,
                q: searchQ || undefined,
            });
            setReleases(data.releases || []);
            setInstallers(data.installers || []);
        } catch (e) {
            setError(e?.response?.data?.error || e.message || 'Failed to load subs');
        } finally {
            setLoading(false);
        }
    }, [paidFilter, installerFilter, searchQ]);

    useEffect(() => {
        if (authorized) load();
    }, [authorized, load]);

    const groups = useMemo(() => groupByInstaller(releases), [releases]);

    const totals = useMemo(() => {
        const unpaid = releases.filter((r) => !r.installer_invoice_paid).length;
        return { total: releases.length, unpaid, paid: releases.length - unpaid };
    }, [releases]);

    const rowKey = (r) => `${r.job}-${r.release}`;
    const hubRow = useMemo(
        () => (hubKey == null ? null : releases.find((r) => rowKey(r) === hubKey) || null),
        [hubKey, releases],
    );

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
        // Archived rows leave the list once marked invoiced complete.
        if (nextPaid && row.is_archived) {
            setReleases((list) => list.filter((r) => rowKey(r) !== key));
        } else {
            patchRow(key, { installer_invoice_paid: nextPaid });
        }
        try {
            await updateInstallerInvoicePaid(row.job, row.release, nextPaid);
        } catch (e) {
            if (nextPaid && row.is_archived) {
                // Restore removed archived row
                setReleases((list) => {
                    if (list.some((r) => rowKey(r) === key)) return list;
                    return [...list, { ...row, installer_invoice_paid: prev }].sort((a, b) => {
                        const ia = (a.installer || '').localeCompare(b.installer || '');
                        if (ia !== 0) return ia;
                        if (a.job !== b.job) return a.job - b.job;
                        return String(a.release).localeCompare(String(b.release));
                    });
                });
            } else {
                patchRow(key, { installer_invoice_paid: prev });
            }
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
            <div className="flex-1 p-4 md:p-6 max-w-[1600px] mx-auto w-full">
                {/* Header — matches SubcontractorAdmin / T&M */}
                <div className="flex items-start sm:items-center justify-between gap-3 mb-4 flex-wrap">
                    <div className="min-w-0">
                        <h1 className="text-xl font-bold text-ink">Invoice Paid</h1>
                        <p className="mt-0.5 text-sm text-ink-3">
                            Sub invoices by installer. Archived releases stay until marked invoiced complete.
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

                    <input
                        type="search"
                        value={searchInput}
                        onChange={(e) => setSearchInput(e.target.value)}
                        placeholder="Search job, name, invoice #…"
                        aria-label="Search releases"
                        className="text-sm rounded-lg border border-hairline bg-surface text-ink px-3 py-1.5 min-w-[12rem] flex-1 max-w-xs focus:outline-none focus:ring-1 focus:ring-accent-500"
                    />

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
                        {searchQ
                            ? `No releases match “${searchQ}”.`
                            : 'No assigned sub releases with outstanding work.'}
                    </div>
                ) : (
                    /* One table for all installers so columns share one layout (no drift). */
                    <div className="overflow-x-auto rounded-xl border border-hairline bg-surface">
                        <table className="w-full text-sm table-fixed min-w-[1320px]">
                            <colgroup>
                                <col style={{ width: '3.5%' }} />
                                <col style={{ width: '3.5%' }} />
                                <col style={{ width: '10%' }} />
                                <col style={{ width: '11.5%' }} />
                                <col style={{ width: '7.5%' }} />
                                <col style={{ width: '7.5%' }} />
                                <col style={{ width: '5.5%' }} />
                                <col style={{ width: '6%' }} />
                                <col style={{ width: '6%' }} />
                                <col style={{ width: '7.5%' }} />
                                <col style={{ width: '8%' }} />
                                <col style={{ width: '6%' }} />
                                <col style={{ width: '9.5%' }} />
                                <col style={{ width: '8%' }} />
                            </colgroup>
                            <thead className="bg-head-bg">
                                <tr>
                                    <th className="px-2 py-2 text-center font-semibold text-ink-3 align-middle">Job</th>
                                    <th className="px-2 py-2 text-center font-semibold text-ink-3 align-middle">Rel</th>
                                    <th className="px-2 py-2 text-center font-semibold text-ink-3 align-middle">Job name</th>
                                    <th className="px-2 py-2 text-center font-semibold text-ink-3 align-middle">Description</th>
                                    <th className="px-2 py-2 text-center font-semibold text-ink-3 align-middle">Stage</th>
                                    <th className="px-2 py-2 text-center font-semibold text-ink-3 align-middle">Start install</th>
                                    <th className="px-2 py-2 text-center font-semibold text-ink-3 align-middle whitespace-nowrap">Status</th>
                                    <th
                                        className="px-2 py-2 text-center font-semibold text-ink-3 align-middle"
                                        title="Install progress from the Job Log (Job Comp) — read-only here"
                                    >
                                        Install Prog
                                    </th>
                                    <th
                                        className="px-2 py-2 text-center font-semibold text-ink-3 align-middle whitespace-nowrap"
                                        title="Install hours from the Job Log — read-only here"
                                    >
                                        Install Hrs
                                    </th>
                                    <th
                                        className="px-2 py-2 text-center font-semibold text-ink-3 align-middle whitespace-nowrap"
                                        title={`Install Hrs × $${INSTALL_RATE_PER_HOUR.toFixed(2)}`}
                                    >
                                        Budget
                                    </th>
                                    <th
                                        className="px-2 py-2 text-center font-semibold text-ink-3 align-middle"
                                        title="Install Prog % × Budget — what the release has earned so far"
                                    >
                                        Est. Billable
                                    </th>
                                    <th className="px-2 py-2 text-center font-semibold text-ink-3 align-middle whitespace-nowrap">Progress</th>
                                    <th className="px-2 py-2 text-center font-semibold text-ink-3 align-middle whitespace-nowrap">Invoice #</th>
                                    <th className="px-2 py-2 text-center font-semibold text-ink-3 align-middle">Invoiced complete</th>
                                </tr>
                            </thead>
                            <tbody>
                                {groups.map(([installer, rows]) => {
                                    const unpaidCount = rows.filter((r) => !r.installer_invoice_paid).length;
                                    return (
                                        <Fragment key={installer}>
                                            <tr className="bg-canvas border-t border-hairline">
                                                <td
                                                    colSpan={14}
                                                    className="px-3 py-2 align-middle"
                                                >
                                                    <div className="flex items-baseline justify-between gap-2">
                                                        <span className="text-sm font-bold text-ink">
                                                            {installer}
                                                        </span>
                                                        <span className="text-xs text-ink-3 font-mono tabular-nums">
                                                            {unpaidCount} unpaid · {rows.length} total
                                                        </span>
                                                    </div>
                                                </td>
                                            </tr>
                                            {rows.map((r) => {
                                                const key = rowKey(r);
                                                const busyPaid = busyKey === `${key}:paid`;
                                                const busyProgress = busyKey === `${key}:progress`;
                                                const busyNumbers = busyKey === `${key}:numbers`;
                                                const budget = installBudget(r.install_hrs);
                                                const billable = estimatedBillable(r.job_comp, r.install_hrs);
                                                return (
                                                    <tr
                                                        key={key}
                                                        className="border-t border-hairline hover:bg-surface-2"
                                                    >
                                                        <td className="px-2 py-2 font-mono tabular-nums text-ink text-center align-middle">
                                                            {r.job}
                                                        </td>
                                                        <td className="px-2 py-2 font-mono tabular-nums text-ink-2 text-center align-middle">
                                                            {r.release}
                                                        </td>
                                                        <td
                                                            className="px-2 py-2 text-ink text-center align-middle cursor-pointer hover:bg-accent-50 dark:hover:bg-slate-600 transition-colors"
                                                            title={r.job_name ? `${r.job_name} — click to open` : 'Click to open'}
                                                            onClick={() => setHubKey(rowKey(r))}
                                                        >
                                                            <span className="line-clamp-2 break-words">{r.job_name || '—'}</span>
                                                        </td>
                                                        <td
                                                            className="px-2 py-2 text-center align-middle cursor-pointer hover:bg-accent-50 dark:hover:bg-slate-600 transition-colors"
                                                            title={r.description ? `${r.description} — click to open` : 'Click to open'}
                                                            onClick={() => setHubKey(rowKey(r))}
                                                        >
                                                            <span className="line-clamp-2 break-words font-medium text-accent-600 dark:text-accent-300 hover:underline">
                                                                {r.description || '—'}
                                                            </span>
                                                        </td>
                                                        <td className="px-2 py-2 text-ink-2 text-center align-middle">
                                                            <span className="line-clamp-2 break-words">{r.stage || '—'}</span>
                                                        </td>
                                                        <td className="px-2 py-2 text-ink-2 text-center align-middle font-mono tabular-nums whitespace-nowrap">
                                                            {fmtDate(r.start_install)}
                                                        </td>
                                                        <td className="px-2 py-2 text-center align-middle whitespace-nowrap">
                                                            {r.is_archived ? (
                                                                <span className="inline-block px-1.5 py-0.5 text-[11px] font-semibold rounded border border-hairline bg-surface-2 text-ink-3">
                                                                    Archived
                                                                </span>
                                                            ) : (
                                                                <span className="inline-block px-1.5 py-0.5 text-[11px] font-semibold rounded border border-emerald-200/80 dark:border-emerald-800/60 bg-emerald-50 dark:bg-emerald-950/40 text-emerald-800 dark:text-emerald-200">
                                                                    Live
                                                                </span>
                                                            )}
                                                        </td>
                                                        <td className="px-2 py-2 text-center align-middle font-mono tabular-nums text-ink-2 whitespace-nowrap">
                                                            {formatInstallProg(r.job_comp) || '—'}
                                                        </td>
                                                        <td
                                                            className="px-2 py-2 text-center align-middle font-mono tabular-nums text-ink-2 whitespace-nowrap"
                                                            title="Install hours from the Job Log — read-only here"
                                                        >
                                                            {formatCellValue(r.install_hrs, 'Install HRS')}
                                                        </td>
                                                        <td
                                                            className="px-2 py-2 text-center align-middle font-mono tabular-nums text-ink whitespace-nowrap"
                                                            title={
                                                                budget == null
                                                                    ? 'No install hours on this release'
                                                                    : `${r.install_hrs} hrs × $${INSTALL_RATE_PER_HOUR.toFixed(2)}`
                                                            }
                                                        >
                                                            {fmtUsd(budget)}
                                                        </td>
                                                        <td
                                                            className="px-2 py-2 text-center align-middle font-mono tabular-nums text-ink whitespace-nowrap"
                                                            title={
                                                                billable == null
                                                                    ? 'Needs both install hours and a Job Log install progress'
                                                                    : `${formatInstallProg(r.job_comp)} of ${fmtUsd(budget)}`
                                                            }
                                                        >
                                                            {fmtUsd(billable)}
                                                        </td>
                                                        <td className="px-2 py-2 text-center align-middle">
                                                            <div className="inline-flex justify-center">
                                                                <ProgressInput
                                                                    value={r.installer_invoice_progress}
                                                                    busy={busyProgress}
                                                                    onCommit={(n) => handleProgress(r, n)}
                                                                />
                                                            </div>
                                                        </td>
                                                        <td className="px-2 py-2 text-center align-middle">
                                                            <div className="flex justify-center w-full">
                                                                <InvoiceNumbersInput
                                                                    value={r.installer_invoice_numbers}
                                                                    busy={busyNumbers}
                                                                    onCommit={(v) => handleInvoiceNumbers(r, v)}
                                                                />
                                                            </div>
                                                        </td>
                                                        <td className="px-2 py-2 text-center align-middle">
                                                            <div className="inline-flex justify-center">
                                                                <PaidToggle
                                                                    paid={!!r.installer_invoice_paid}
                                                                    busy={busyPaid}
                                                                    onChange={(next) => handleToggle(r, next)}
                                                                />
                                                            </div>
                                                        </td>
                                                    </tr>
                                                );
                                            })}
                                        </Fragment>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>

            {/* Same release hub the Job Log opens — Details / Attachments / Change Log. */}
            <ReleaseHubModal
                isOpen={hubRow != null}
                onClose={() => setHubKey(null)}
                job={hubRow}
                releaseId={hubRow?.id}
                viewerUrl={hubRow?.viewer_url}
                initialTab="details"
                onNotesChanged={(notes) => {
                    if (hubKey != null) patchRow(hubKey, { notes });
                }}
            />
        </div>
    );
}

function boolEq(a, b) {
    return !!a === !!b;
}
