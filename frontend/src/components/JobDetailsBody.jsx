/**
 * @milehigh-header
 * schema_version: 1
 * purpose: The Details pane of the release hub — a two-column dossier (Schedule/Assignment, Production/Materials) plus the stage progress ladder, per the Aug 2026 redesign handoff §4.
 * exports:
 *   JobDetailsBody: The detail sections, with no dialog chrome, for a host modal to place
 * imports_from: [react, ../services/jobsApi, ../constants/columnHeaders, ../utils/stageTint]
 * imported_by: [frontend/src/components/ReleaseHubModal.jsx]
 * invariants:
 *   - Owns its own data fetch, so it loads when mounted rather than on an isOpen flag
 *   - Reads display keys ('Ship Date') with a raw-key fallback ('ship_date') so Job Log and
 *     Timeline rows both render — the two surfaces serialize releases slightly differently
 *   - External links (Events/Procore/Trello) live in the host's header, and the notes thread
 *     in the host's right rail; neither belongs here
 * updated_by_agent: 2026-08-06T00:00:00Z
 */
import React, { useState, useEffect, useRef } from 'react';

import { jobsApi } from '../services/jobsApi';
import { HEADER_OVERRIDES } from '../constants/columnHeaders';
import { stageTint, STAGE_LADDER, stageLadderIndex } from '../utils/stageTint';
import { RELEASE_TAGS } from '../constants/releaseTags';

// Label a field exactly as the Job Log table headers it, so the modal and the
// table speak the same language ('Job Comp' reads "Install Prog" in both).
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

/** Uppercase section rule. `stacked` adds the top gap for a second section in the same column. */
function SectionLabel({ children, stacked = false }) {
    return (
        <div
            className="text-jl-label font-bold uppercase text-ink-3 border-b border-hairline-strong"
            style={{ paddingTop: stacked ? 20 : 0, paddingBottom: 6 }}
        >
            {children}
        </div>
    );
}

/**
 * One label/value line. An empty value renders an em dash rather than collapsing
 * the row — a blank Invoiced is information, and dropping the line hides it.
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

export function JobDetailsBody({ job, scrollToMaterials = false, onOrdersChanged = null }) {
    const [materialOrders, setMaterialOrders] = useState([]);
    const [ordersLoading, setOrdersLoading] = useState(false);
    const materialsRef = useRef(null);
    const [releaseTag, setReleaseTag] = useState(() => job?.release_tag || '');
    const [tagSaving, setTagSaving] = useState(false);
    const [tagError, setTagError] = useState(null);

    const jobId = job ? (job['Job #'] || job.job) : null;
    const relId = job ? (job['Release #'] || job.release) : null;

    useEffect(() => {
        setReleaseTag(job?.release_tag || '');
        setTagError(null);
    }, [job?.id, job?.release_tag, jobId, relId]);

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
            // Let the Job Log refresh its Mats column right away rather than
            // waiting for the next poll.
            if (onOrdersChanged) onOrdersChanged();
        } catch {
            // Leave the row unchanged (e.g. insufficient permissions).
        }
    };

    const handleReleaseTagChange = async (next) => {
        if (!jobId || relId == null) return;
        const prev = releaseTag;
        setReleaseTag(next);
        setTagSaving(true);
        setTagError(null);
        try {
            await jobsApi.updateJobFields(jobId, relId, { release_tag: next || null });
            if (job) job.release_tag = next || null;
        } catch (err) {
            setReleaseTag(prev);
            setTagError(err.message || 'Could not update billing tag');
        } finally {
            setTagSaving(false);
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

    const stage = pick('Stage', 'stage');
    const currentStageIdx = stageLadderIndex(stage);
    const tint = stageTint(stage);

    return (
        <div>
            <div className="grid grid-cols-1 lg:grid-cols-2" style={{ gap: '0 28px' }}>
                <div className="min-w-0">
                    <SectionLabel>Schedule</SectionLabel>
                    <Field label={labelFor('Released')} value={formatDate(pick('Released', 'released'))} />
                    <Field label={labelFor('Ship Date')} value={formatDate(pick('Ship Date', 'ship_date'))} />
                    <Field
                        label={labelFor('Start install')}
                        value={isAsap ? 'ASAP' : startInstall}
                        flag={isAsap ? <MiniFlag kind="ASAP" /> : (isHardDate ? <MiniFlag kind="HARD" /> : null)}
                    />
                    <Field
                        label={labelFor('Comp. ETA')}
                        value={formatDate(pick('Comp. ETA', 'comp_eta') || job.comp_eta_effective)}
                    />

                    <SectionLabel stacked>Assignment</SectionLabel>
                    <Field label={labelFor('PM')} value={pick('PM', 'pm')} mono={false} />
                    <Field label={labelFor('BY')} value={pick('BY', 'by')} mono={false} />
                    <Field label="Installer" value={job.installer} mono={false} />
                    <Field label="Crew" value={job.num_guys} />
                    <Field label={labelFor('Install HRS')} value={pick('Install HRS', 'install_hrs')} />
                    <Field label={labelFor('Paint color')} value={pick('Paint color', 'paint_color')} mono={false} />
                </div>

                <div className="min-w-0">
                    <SectionLabel>Billing</SectionLabel>
                    <div className="flex items-center justify-between gap-3 border-b border-hairline" style={{ padding: '8px 2px' }}>
                        <span className="text-jl text-ink-2 shrink-0">Billing tag</span>
                        <select
                            value={releaseTag || ''}
                            onChange={(e) => handleReleaseTagChange(e.target.value)}
                            disabled={tagSaving}
                            className="font-semibold text-right text-ink bg-transparent border border-hairline-strong rounded-md"
                            style={{ fontSize: 13, padding: '4px 8px', minWidth: 140 }}
                            title="Contracted / Change Order / MHMW Cost — not shown on the job log row"
                        >
                            <option value="">— unset —</option>
                            {RELEASE_TAGS.map((t) => (
                                <option key={t.value} value={t.value}>{t.label}</option>
                            ))}
                        </select>
                    </div>
                    {tagError && (
                        <p className="text-jl-2 text-red-600 dark:text-red-400" style={{ padding: '4px 2px' }}>{tagError}</p>
                    )}
                    {!releaseTag && (
                        <p className="text-jl-2 text-ink-3 italic" style={{ padding: '4px 2px' }}>
                            Not set (legacy row). Tag is required on new releases.
                        </p>
                    )}

                    <SectionLabel stacked>Production</SectionLabel>
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
                    <Field label={labelFor('Job Comp')} value={pick('Job Comp', 'job_comp')} />
                    <Field label={labelFor('Invoiced')} value={pick('Invoiced', 'invoiced')} />

                    <div ref={materialsRef}>
                        <SectionLabel stacked>Materials ordered</SectionLabel>
                        {ordersLoading ? (
                            <p className="text-jl text-ink-3 italic" style={{ padding: '8px 2px' }}>Loading…</p>
                        ) : materialOrders.length === 0 ? (
                            <p className="text-jl text-ink-3 italic" style={{ padding: '8px 2px' }}>None ordered.</p>
                        ) : (
                            materialOrders.map((o) => {
                                // Status orders (galvanizing / stock) track a planning→complete
                                // shipping lifecycle, not the itemized ordered/received toggle.
                                const isStatusOrder = Boolean(o.shipping_status);
                                const received = o.status === 'received';
                                const complete = o.shipping_status === 'complete';
                                const badgeLabel = isStatusOrder
                                    ? (complete ? 'Complete' : 'Planning')
                                    : (received ? 'Received' : 'Ordered');
                                // Status pills reuse the stage tints (handoff §4).
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
                </div>
            </div>

            <div style={{ marginTop: 22 }}>
                <SectionLabel>Stage progress</SectionLabel>
                {/* One bar segment per stage: past = accent, current = the stage's
                    own tint, future = grid grey. The handoff labels every segment,
                    but it drew a 7-stage ladder — the real one is 17, and 17 labels
                    at this width truncate to "Relea… Materi… Cut St…", which reads
                    as noise. Only the ends and the current stage are named; the
                    rest carry their name as a tooltip. */}
                <div className="flex items-stretch" style={{ gap: 4, marginTop: 12 }}>
                    {STAGE_LADDER.map((s, i) => {
                        const isCurrent = i === currentStageIdx;
                        const isPast = currentStageIdx >= 0 && i < currentStageIdx;
                        const bar = isCurrent ? tint.fg : (isPast ? 'var(--accent)' : 'var(--grid)');
                        return (
                            <div key={s} className="flex-1 min-w-0" title={s}>
                                <div style={{ height: 5, borderRadius: 3, background: bar }} />
                            </div>
                        );
                    })}
                </div>
                <div className="flex items-baseline justify-between gap-3" style={{ marginTop: 8 }}>
                    <span className="text-jl-2 text-ink-3">{STAGE_LADDER[0]}</span>
                    {currentStageIdx >= 0 ? (
                        <span className="text-jl font-bold text-ink">
                            {stage}
                            <span className="text-ink-3 font-medium">
                                {` · step ${currentStageIdx + 1} of ${STAGE_LADDER.length}`}
                            </span>
                        </span>
                    ) : (
                        <span className="text-jl-2 text-ink-3 italic">Stage not on the ladder</span>
                    )}
                    <span className="text-jl-2 text-ink-3">{STAGE_LADDER[STAGE_LADDER.length - 1]}</span>
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
