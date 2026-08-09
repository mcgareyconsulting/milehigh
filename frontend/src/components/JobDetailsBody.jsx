/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Details pane of the release hub — date-flow hero, 3-col metadata
 *   (Assignment / Production / Materials), banana-code stage progress at bottom.
 * exports:
 *   JobDetailsBody: Detail sections only (no dialog chrome) for a host modal
 *   formatInstallProg: Job Comp → display string (whole number + %, X, or —)
 * imports_from: [react, ../services/jobsApi, ../constants/columnHeaders, ../utils/stageTint,
 *   ./StageIconRow]
 * imported_by: [frontend/src/components/ReleaseHubModal.jsx]
 * invariants:
 *   - Owns its own material-orders fetch when mounted
 *   - Reads display keys ('Ship Date') with raw-key fallback ('ship_date')
 *   - External links live in the host header; Activity rail is host-owned
 *   - UI only: no new write paths except existing mark-received on orders
 * updated_by_agent: 2026-08-08T00:00:00Z
 */
import React, { useState, useEffect, useRef } from 'react';

import { jobsApi } from '../services/jobsApi';
import { HEADER_OVERRIDES } from '../constants/columnHeaders';
import { stageTint } from '../utils/stageTint';
import { StageIconRow } from './StageIconRow';

/** Slightly larger than the table column so the icons read at modal scale. */
const MODAL_BANANA_ICON_SIZE = 36;

const labelFor = (key) => HEADER_OVERRIDES[key] || key;

// Date-only ("2026-06-15") formatter that avoids the UTC-midnight off-by-one
// a bare new Date(...) would introduce in negative-offset timezones.
const formatDate = (dateString) => {
    if (!dateString) return null;
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(dateString));
    const date = m
        ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]))
        : new Date(dateString);
    if (isNaN(date)) return String(dateString);
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
};

const formatTimeAgo = (dateString) => {
    if (!dateString) return null;
    try {
        const diffMinutes = Math.floor((new Date() - new Date(dateString)) / 60000);
        const diffHours = Math.floor(diffMinutes / 60);
        const diffDays = Math.floor(diffHours / 24);
        if (diffDays > 0) return `${diffDays} day${diffDays !== 1 ? 's' : ''} ago`;
        if (diffHours > 0) return `${diffHours} hour${diffHours !== 1 ? 's' : ''} ago`;
        if (diffMinutes > 0) return `${diffMinutes} minute${diffMinutes !== 1 ? 's' : ''} ago`;
        return 'just now';
    } catch {
        return null;
    }
};

/**
 * Install Prog (Job Comp) display:
 *   blank / O → null (caller renders —)
 *   X → "X"
 *   whole number → "75%" (no decimal handling)
 */
export function formatInstallProg(raw) {
    if (raw == null || raw === false) return null;
    const s = String(raw).trim();
    if (!s || s.toUpperCase() === 'O') return null;
    if (s.toUpperCase() === 'X') return 'X';
    // Whole digits only — reject decimals / junk.
    if (/^\d+$/.test(s)) return `${s}%`;
    return s;
}

/** Uppercase section rule. Optional `action` sits on the right of the same line. */
function SectionLabel({ children, action = null }) {
    return (
        <div
            className="flex items-center justify-between gap-2 border-b border-hairline-strong"
            style={{ paddingBottom: 6 }}
        >
            <span className="text-jl-label font-bold uppercase text-ink-3 min-w-0">
                {children}
            </span>
            {action}
        </div>
    );
}

/**
 * One label/value line. Empty value → em dash (blank Invoiced is still information).
 */
function Field({ label, value, mono = true, flag = null }) {
    const blank = value == null || value === '' || value === false;
    return (
        <div className="flex items-center justify-between gap-3 border-b border-hairline" style={{ padding: '8px 2px' }}>
            <span className="text-jl text-ink-2 shrink-0">{label}</span>
            <span className="flex items-center gap-[7px] min-w-0">
                {flag}
                <span
                    className={`font-semibold text-right break-words ${mono ? 'font-mono' : ''} ${blank ? 'text-ink-3' : 'text-ink'}`}
                    style={{ fontSize: 13 }}
                >
                    {blank ? '—' : value}
                </span>
            </span>
        </div>
    );
}

/** ASAP / HARD mini-flags beside a schedule date, reusing the table's flag tints. */
function MiniFlag({ kind }) {
    const cls = kind === 'ASAP' ? 'jl-flag-red' : 'jl-flag-green';
    return (
        <span
            className={`${cls} font-bold uppercase`}
            style={{ fontSize: 10, letterSpacing: '.05em', padding: '2px 6px', borderRadius: 4 }}
        >
            {kind}
        </span>
    );
}

function FlowArrow() {
    return (
        <span
            aria-hidden
            className="shrink-0"
            style={{
                color: 'var(--border-strong)',
                fontSize: 17,
                padding: '0 4px',
                lineHeight: 1,
                alignSelf: 'center',
            }}
        >
            →
        </span>
    );
}

/**
 * One cell in the date-flow hero: uppercase label + mono value (+ optional flag).
 */
function FlowCell({ label, value, flag = null, accent = false }) {
    const blank = value == null || value === '' || value === false;
    return (
        <div className="min-w-0" style={{ flex: '1 1 0' }}>
            <div
                className="font-bold uppercase flex items-center flex-wrap"
                style={{
                    fontSize: 10,
                    letterSpacing: '.04em',
                    color: 'var(--text-3)',
                    gap: 6,
                    marginBottom: 4,
                }}
            >
                <span>{label}</span>
                {flag}
            </div>
            <div
                className="font-mono font-semibold truncate"
                style={{
                    fontSize: 15,
                    fontWeight: 600,
                    color: blank
                        ? '#9aa3b2'
                        : (accent ? 'var(--accent)' : 'var(--text)'),
                }}
                title={blank ? undefined : String(value)}
            >
                {blank ? '—' : value}
            </div>
        </div>
    );
}

export function JobDetailsBody({ job, scrollToMaterials = false, onOrdersChanged = null }) {
    const [materialOrders, setMaterialOrders] = useState([]);
    const [ordersLoading, setOrdersLoading] = useState(false);
    const [markAllBusy, setMarkAllBusy] = useState(false);
    const materialsRef = useRef(null);

    const jobId = job ? (job['Job #'] || job.job) : null;
    const relId = job ? (job['Release #'] || job.release) : null;

    useEffect(() => {
        if (jobId == null) return;
        let cancelled = false;
        setOrdersLoading(true);
        jobsApi.getMaterialOrders(jobId, relId)
            .then((data) => { if (!cancelled) setMaterialOrders(data?.orders || []); })
            .catch(() => { if (!cancelled) setMaterialOrders([]); })
            .finally(() => { if (!cancelled) setOrdersLoading(false); });
        return () => { cancelled = true; };
    }, [jobId, relId]);

    // When opened from a material-order chip, bring the Materials section into
    // view once its data has settled.
    useEffect(() => {
        if (!scrollToMaterials || ordersLoading) return;
        const el = materialsRef.current;
        if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, [scrollToMaterials, ordersLoading]);

    const handleToggleReceived = async (order) => {
        const next = order.status !== 'received';
        try {
            const data = await jobsApi.markMaterialOrderReceived(order.id, next);
            setMaterialOrders((prev) =>
                prev.map((o) => (o.id === order.id ? (data?.order || o) : o))
            );
            if (onOrdersChanged) onOrdersChanged();
        } catch {
            // Leave the row unchanged (e.g. insufficient permissions).
        }
    };

    // Itemized orders only (not galvanizing/stock shipping_status rows).
    const pendingReceivable = materialOrders.filter(
        (o) => !o.shipping_status && o.status !== 'received'
    );

    const handleMarkAllReceived = async () => {
        if (!pendingReceivable.length || markAllBusy) return;
        setMarkAllBusy(true);
        try {
            const results = await Promise.all(
                pendingReceivable.map((o) =>
                    jobsApi.markMaterialOrderReceived(o.id, true)
                        .then((data) => ({ id: o.id, order: data?.order || { ...o, status: 'received' } }))
                        .catch(() => null)
                )
            );
            const byId = new Map(
                results.filter(Boolean).map((r) => [r.id, r.order])
            );
            if (byId.size > 0) {
                setMaterialOrders((prev) =>
                    prev.map((o) => (byId.has(o.id) ? byId.get(o.id) : o))
                );
                if (onOrdersChanged) onOrdersChanged();
            }
        } finally {
            setMarkAllBusy(false);
        }
    };

    if (!job) return null;

    // Display key first, raw key second — Job Log rows carry the former, some
    // Timeline/API paths only the latter.
    const pick = (displayKey, rawKey) => {
        const v = job[displayKey];
        return v == null || v === '' ? job[rawKey] : v;
    };

    const lastUpdatedAt = pick('Last Updated At', 'last_updated_at');
    const sourceOfUpdate = pick('Source Of Update', 'source_of_update');
    const isAsap = job.start_install_asap === true;
    // A hard date is an explicit commitment rather than a formula result — the
    // same test the Job Log's Start install cell uses to paint its green flag.
    const isHardDate = !isAsap
        && job.start_install_no_color !== true
        && job.start_install_formulaTF === false
        && Boolean(pick('Start install', 'start_install'));
    const startInstall = formatDate(pick('Start install', 'start_install'));
    const startInstallDisplay = isAsap ? 'ASAP' : startInstall;
    const startFlag = isAsap
        ? <MiniFlag kind="ASAP" />
        : (isHardDate ? <MiniFlag kind="HARD" /> : null);

    const stage = pick('Stage', 'stage');
    const tint = stageTint(stage);
    const installProg = formatInstallProg(pick('Job Comp', 'job_comp'));

    const materialsBlock = (
        <div ref={materialsRef}>
            {ordersLoading ? (
                <p className="text-jl text-ink-3 italic" style={{ padding: '8px 2px' }}>Loading…</p>
            ) : materialOrders.length === 0 ? (
                <p className="text-jl text-ink-3 italic" style={{ padding: '8px 2px' }}>None ordered.</p>
            ) : (
                materialOrders.map((o) => {
                    const isStatusOrder = Boolean(o.shipping_status);
                    const received = o.status === 'received';
                    const complete = o.shipping_status === 'complete';
                    const badgeLabel = isStatusOrder
                        ? (complete ? 'Complete' : 'Planning')
                        : (received ? 'Received' : 'Ordered');
                    const done = isStatusOrder ? complete : received;
                    const pill = done
                        ? { bg: 'var(--st-green-bg)', fg: 'var(--st-green-fg)' }
                        : { bg: 'var(--st-amber-bg)', fg: 'var(--st-amber-fg)' };
                    const meta = [o.supplier, o.po_number ? `PO ${o.po_number}` : null]
                        .filter(Boolean).join(' · ');
                    return (
                        <div key={o.id} className="border-b border-hairline" style={{ padding: '8px 2px' }}>
                            <div className="flex items-center justify-between gap-3">
                                <span className="text-jl text-ink-2 min-w-0 truncate">
                                    {o.quantity != null ? `(${o.quantity}) ` : ''}{o.description}
                                </span>
                                <span className="flex items-center gap-2 shrink-0">
                                    {!isStatusOrder && (
                                        <button
                                            onClick={() => handleToggleReceived(o)}
                                            className="text-jl-2 text-brand hover:underline"
                                        >
                                            {received ? 'Mark ordered' : 'Mark received'}
                                        </button>
                                    )}
                                    <span
                                        className="inline-block font-semibold"
                                        style={{ padding: '2px 8px', borderRadius: 5, fontSize: 11.5, background: pill.bg, color: pill.fg }}
                                    >
                                        {badgeLabel}
                                    </span>
                                </span>
                            </div>
                            {(meta || o.ordered_by || o.ordered_at) && (
                                <p className="text-jl-2 text-ink-3 mt-0.5">
                                    {[meta, o.ordered_by ? `Ordered by ${o.ordered_by}` : null,
                                        o.ordered_at ? formatDate(o.ordered_at) : null]
                                        .filter(Boolean).join(' · ')}
                                </p>
                            )}
                        </div>
                    );
                })
            )}
        </div>
    );

    return (
        <div>
            {/* ── Date flow hero ─────────────────────────────────────────── */}
            <div
                className="border border-hairline bg-surface-2"
                style={{ borderRadius: 10, padding: '16px 20px', marginBottom: 22 }}
            >
                <div className="flex items-stretch min-w-0" style={{ gap: 0 }}>
                    <FlowCell label="Released" value={formatDate(pick('Released', 'released'))} />
                    <FlowArrow />
                    <FlowCell label="Ship Date" value={formatDate(pick('Ship Date', 'ship_date'))} />
                    <FlowArrow />
                    <FlowCell
                        label="Start Install"
                        value={startInstallDisplay}
                        flag={startFlag}
                    />
                    <FlowArrow />
                    <FlowCell
                        label="Comp. ETA"
                        value={formatDate(pick('Comp. ETA', 'comp_eta') || job.comp_eta_effective)}
                    />
                    <div
                        aria-hidden
                        className="shrink-0 self-stretch"
                        style={{
                            width: 1,
                            background: 'var(--border)',
                            margin: '0 16px',
                        }}
                    />
                    <FlowCell label="Install Prog" value={installProg} accent />
                </div>
            </div>

            {/* ── Metadata: Assignment · Production · Materials ──────────── */}
            <div
                className="grid"
                style={{
                    gridTemplateColumns: '1fr 1fr 1fr',
                    columnGap: 30,
                    rowGap: 20,
                }}
            >
                <div className="min-w-0">
                    <SectionLabel>Assignment</SectionLabel>
                    <Field label={labelFor('PM')} value={pick('PM', 'pm')} mono={false} />
                    <Field label={labelFor('BY')} value={pick('BY', 'by')} mono={false} />
                    <Field label="Installer" value={job.installer} mono={false} />
                    <Field label="Crew" value={job.num_guys} />
                    <Field label={labelFor('Install HRS')} value={pick('Install HRS', 'install_hrs')} />
                    <Field label={labelFor('Paint color')} value={pick('Paint color', 'paint_color')} mono={false} />
                </div>

                <div className="min-w-0">
                    <SectionLabel>Production</SectionLabel>
                    <Field
                        label={labelFor('Stage')}
                        mono={false}
                        value={stage ? (
                            <span
                                className="inline-block font-semibold"
                                style={{ padding: '3px 9px', borderRadius: 5, fontSize: 11.5, background: tint.bg, color: tint.fg }}
                            >
                                {stage}
                            </span>
                        ) : null}
                    />
                    <Field label="Stage Group" value={pick('Stage Group', 'stage_group')} mono={false} />
                    <Field label={labelFor('Fab Order')} value={pick('Fab Order', 'fab_order')} />
                    <Field label={labelFor('Fab Hrs')} value={pick('Fab Hrs', 'fab_hrs')} />
                    <Field label={labelFor('Job Comp')} value={installProg} />
                    <Field label={labelFor('Invoiced')} value={pick('Invoiced', 'invoiced')} />
                </div>

                <div className="min-w-0">
                    <SectionLabel
                        action={pendingReceivable.length > 0 ? (
                            <button
                                type="button"
                                onClick={handleMarkAllReceived}
                                disabled={markAllBusy}
                                className="text-brand font-semibold bg-transparent border-0 cursor-pointer disabled:opacity-50 shrink-0"
                                style={{ fontSize: 11.5 }}
                            >
                                {markAllBusy ? 'Marking…' : 'Mark all received'}
                            </button>
                        ) : null}
                    >
                        Materials ordered
                    </SectionLabel>
                    {materialsBlock}
                </div>
            </div>

            {/* ── Stage progress (banana code) ───────────────────────────── */}
            <div style={{ marginTop: 22 }}>
                <SectionLabel>Stage progress</SectionLabel>
                <div className="flex flex-col items-center" style={{ marginTop: 14, gap: 10 }}>
                    <StageIconRow stage={stage} iconSize={MODAL_BANANA_ICON_SIZE} />
                    {stage ? (
                        <span className="text-jl font-bold text-ink">{stage}</span>
                    ) : (
                        <span className="text-jl-2 text-ink-3 italic">No stage set</span>
                    )}
                </div>
            </div>

            {lastUpdatedAt && (
                <p className="text-jl-2 text-ink-3" style={{ marginTop: 18 }}>
                    Updated {formatTimeAgo(lastUpdatedAt)}
                    {sourceOfUpdate ? ` · Source ${sourceOfUpdate}` : ''}
                </p>
            )}
        </div>
    );
}

export default JobDetailsBody;
