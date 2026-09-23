/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Splices tab of the release hub (roadmap T9) — the original release and every splice
 *   under it (340.1, 340.2 …) with the install-hour math laid out two ways: one continuous bar
 *   (Original | Splices | Additional, widths proportional to hours) and a group table with a
 *   subtotal row (the statement-style ledger was dropped 2026-09-18 as redundant with it). Each
 *   row opens that release in the same hub, mirror-card style, so you can move back and forth
 *   across the group.
 * exports:
 *   SplicesPane: Splices tab body for one release (original or splice)
 * imports_from: [react, react-dom, ../services/jobsApi, ../utils/stageTint, ../constants/splices,
 *   ./JobDetailsBody, ./SpliceReleaseModal]
 * imported_by: [frontend/src/components/ReleaseHubModal.jsx]
 * invariants:
 *   - Spec: Bill, 2026-09-16 shop session; facelift 2026-09-18 (Design canvas "Splices Tab
 *     Facelift", Option A). Replaces the Splices section that sat buried in Details.
 *   - GET /splices answers for the ORIGINAL whether this row is the original or a splice, so the
 *     pane reads the same from either side; + Splice always creates under the original.
 *   - Every number is the server's: total/allocated/remaining (the pool split), plus
 *     additional_install_hrs and group_install_hrs from pool_summary. The pane never adds a
 *     split up itself; the bar's flex weights are those same numbers.
 *   - Pool numbers are BUDGET hours. Additional hours sit outside the pool and are flagged per
 *     splice with their reason; the bar draws them as a separate amber segment after the pool.
 *   - The original's line shows what it still installs ITSELF (pool minus spliced), the same number
 *     the Job Log and Subs → Invoice Paid show for it — its stored install_hrs stays the whole pool.
 *     So the table's Budget Hours column sums straight to the pool.
 *   - Clicking a table row opens a side panel on the right with that release's Schedule, Details
 *     and to-dos — JobDetailsBody in `compact` mode, so edits there are the same writes as the
 *     Details tab. The release number still opens the row in the hub (onOpenRelease); the row
 *     being viewed is marked and its number is not a link.
 *   - The table is numbers only — no hour controls. Budget Hours for the original is what it
 *     still installs itself, so the column sums straight to the pool.
 * updated_by_agent: 2026-09-18T00:00:00Z
 */
import React, { useCallback, useEffect, useState } from 'react';
import { createPortal } from 'react-dom';

import { jobsApi } from '../services/jobsApi';
import { stageTint } from '../utils/stageTint';
import { MANY_SPLICES_THRESHOLD, hasManySplices } from '../constants/splices';
import { JobDetailsBody } from './JobDetailsBody';
import { SpliceReleaseModal } from './SpliceReleaseModal';

const fmtHrs = (v) => (v == null ? '—' : `${Number(v)}`);
const num = (v) => (v == null || v === '' ? null : (Number.isFinite(Number(v)) ? Number(v) : null));
const releaseLabel = (row) => `${row.job}-${row.release}`;
/** Table number cells: 0 or blank from data entry both read as 0, never a dash. */
const cellHrs = (v) => `${num(v) ?? 0}`;

const LABEL = 'text-jl-label font-bold uppercase text-ink-3';
const CARD = { border: '1px solid var(--border)', borderRadius: 10, background: 'var(--surface)' };

function StageChip({ stage }) {
    const tint = stageTint(stage || 'Released');
    return (
        <span
            className="inline-block font-semibold whitespace-nowrap"
            style={{ fontSize: 11.5, padding: '2px 8px', borderRadius: 999, background: tint.bg, color: tint.fg }}
        >
            {stage || 'Released'}
        </span>
    );
}

/** The release number as the thing you click to open it; plain text on the row being viewed. */
function ReleaseLink({ row, isCurrent, onOpen }) {
    const label = releaseLabel(row);
    if (isCurrent || !onOpen) {
        return <span className="font-bold whitespace-nowrap" style={{ color: 'var(--accent)' }}>{label}</span>;
    }
    return (
        <button
            type="button"
            onClick={(e) => { e.stopPropagation(); onOpen(row.id); }}
            title={`Open ${label}`}
            className="bg-transparent border-0 p-0 font-bold whitespace-nowrap cursor-pointer hover:underline"
            style={{ color: 'var(--accent)', font: 'inherit', fontWeight: 700 }}
        >
            {label}
        </button>
    );
}

/**
 * One continuous bar: Original | Splices (one slice per splice that drew budget hours) |
 * Additional. Widths are the hours themselves as flex weights, so 2 : 10 : 14 of 26 reads as
 * such. A 3px gap separates the three kinds, 1px separates splices from each other; each kind
 * is its own rounded block (outlines drawn inset so they follow the corners instead of being
 * clipped). The legend under it carries the words, so a thin segment still reads. Splices with
 * no budget hours draw nothing from the pool and are left out of the bar and its legend.
 */
function HoursBar({ parent, own, pool, allocated, splices, additional }) {
    const budgeted = splices
        .map((sp) => ({ sp, hrs: num(sp.budget_install_hrs ?? sp.install_hrs) || 0 }))
        .filter((s) => s.hrs > 0);
    const ownHrs = own || 0;
    const groups = [
        ownHrs > 0 ? 'own' : null,
        allocated > 0 ? 'splices' : null,
        additional > 0 ? 'addl' : null,
    ].filter(Boolean);
    if (groups.length === 0) return null;

    const seg = (hrs, extra) => ({
        flex: `${hrs} 1 0%`,
        minWidth: 0,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 6,
        overflow: 'hidden',
        whiteSpace: 'nowrap',
        fontSize: 13.5,
        fontWeight: 700,
        ...extra,
    });
    const parentLabel = releaseLabel(parent);
    const swatch = (style) => (
        <span aria-hidden="true" className="inline-block shrink-0" style={{ width: 10, height: 10, borderRadius: 2, boxSizing: 'border-box', ...style }} />
    );

    return (
        <div className="space-y-2" data-testid="hours-bar">
            <div role="img" aria-label={`Install hours: ${fmtHrs(ownHrs)} left on ${parentLabel}, ${fmtHrs(allocated)} spliced off, ${fmtHrs(additional)} additional`}
                style={{ display: 'flex', gap: 3, height: 32 }}>
                {ownHrs > 0 && (
                    <div
                        title={`${parentLabel} still installs ${fmtHrs(ownHrs)} hrs itself`}
                        style={seg(ownHrs, { background: 'var(--accent-soft)', boxShadow: 'inset 0 0 0 1px var(--accent)', color: 'var(--accent)', borderRadius: 6 })}
                    >
                        {fmtHrs(ownHrs)}
                    </div>
                )}
                {allocated > 0 && (
                    <div style={{ flex: `${allocated} 1 0%`, minWidth: 0, display: 'flex', gap: 1, borderRadius: 6, overflow: 'hidden' }}>
                        {budgeted.map(({ sp, hrs }) => (
                            <div
                                key={sp.id}
                                title={`${releaseLabel(sp)} drew ${fmtHrs(hrs)} hrs from the pool`}
                                style={seg(hrs, { background: 'var(--accent)', color: 'var(--accent-ink)' })}
                            >
                                <span>{fmtHrs(hrs)}</span>
                                <span style={{ fontWeight: 400, opacity: 0.9 }}>{releaseLabel(sp)}</span>
                            </div>
                        ))}
                    </div>
                )}
                {additional > 0 && (
                    <div
                        title={`${fmtHrs(additional)} additional hrs, outside the pool`}
                        style={seg(additional, { background: 'var(--fl-amber-bg)', color: 'var(--fl-amber-fg)', borderRadius: 6 })}
                    >
                        +{fmtHrs(additional)}
                    </div>
                )}
            </div>

            <div className="flex flex-wrap gap-x-5 gap-y-1 text-jl-2 text-ink-2">
                <span className="flex items-center gap-1.5">
                    {swatch({ background: 'var(--accent-soft)', boxShadow: 'inset 0 0 0 1px var(--accent)' })}
                    <span className="font-semibold text-ink">Original</span>
                    <span>
                        {pool == null
                            ? 'no install hours yet'
                            : allocated > 0
                                ? `${fmtHrs(ownHrs)} hrs left of a ${fmtHrs(pool)} hr pool`
                                : `${fmtHrs(pool)} hrs, none spliced off`}
                    </span>
                </span>
                {budgeted.length > 0 && (
                    <span className="flex items-center gap-1.5">
                        {swatch({ background: 'var(--accent)' })}
                        <span className="font-semibold text-ink">Splices</span>
                        <span>{fmtHrs(allocated)} hrs from the pool</span>
                        <span className="text-ink-3">
                            {budgeted.map(({ sp, hrs }) => `${releaseLabel(sp)} ${fmtHrs(hrs)}`).join(' · ')}
                        </span>
                    </span>
                )}
                {additional > 0 && (
                    <span className="flex items-center gap-1.5">
                        {swatch({ background: 'var(--fl-amber-bg)' })}
                        <span className="font-semibold text-ink">Additional</span>
                        <span>+{fmtHrs(additional)} hrs, outside the pool</span>
                    </span>
                )}
            </div>
        </div>
    );
}

const TH = 'text-left font-bold uppercase text-ink-3 whitespace-nowrap';
const thStyle = { fontSize: 11.5, letterSpacing: '.05em', padding: '8px 10px', background: 'var(--head-bg)' };
const tdStyle = { padding: '10px 10px', verticalAlign: 'middle', borderTop: '1px solid var(--border)' };
const numCell = { ...tdStyle, textAlign: 'right', whiteSpace: 'nowrap' };

/** The group as a table: one row per release, subtotal at the foot, every column adds up. */
function GroupTable({
    parent, splices, releaseId, onOpen, pool, own, additional, selectedId, onSelect,
}) {
    const parentIsCurrent = parent.id === releaseId;
    const rowProps = (row, isCurrent) => {
        const selected = row.id === selectedId;
        const shadows = [
            isCurrent ? 'inset 3px 0 0 var(--accent)' : null,
            selected ? 'inset 0 0 0 2px var(--accent)' : null,
        ].filter(Boolean);
        return {
            'aria-current': isCurrent ? 'true' : undefined,
            'aria-selected': selected ? 'true' : undefined,
            onClick: () => onSelect(selected ? null : row.id),
            title: selected ? 'Hide details' : `Show details for ${releaseLabel(row)}`,
            className: 'cursor-pointer hover:bg-surface-2',
            style: {
                background: isCurrent ? 'var(--accent-soft)' : selected ? 'var(--surface-2)' : undefined,
                boxShadow: shadows.length ? shadows.join(', ') : undefined,
            },
        };
    };
    const rowCount = 1 + splices.length;
    return (
        <div style={{ ...CARD, overflow: 'auto' }} data-testid="group-table">
            <table className="w-full border-collapse text-jl text-ink" style={{ minWidth: 720 }}>
                <thead>
                    <tr>
                        <th scope="col" className={TH} style={thStyle}>Release</th>
                        <th scope="col" className={TH} style={{ ...thStyle, width: '100%' }}>Description</th>
                        <th scope="col" className={TH} style={thStyle}>Stage</th>
                        <th scope="col" className={TH} style={thStyle}>Installer</th>
                        <th scope="col" className={TH} style={{ ...thStyle, textAlign: 'right' }}>Budget Hours</th>
                        <th scope="col" className={TH} style={{ ...thStyle, textAlign: 'right' }}>Additional Hours</th>
                    </tr>
                </thead>
                <tbody>
                    <tr {...rowProps(parent, parentIsCurrent)}>
                        <td style={tdStyle}><ReleaseLink row={parent} isCurrent={parentIsCurrent} onOpen={onOpen} /></td>
                        <td style={tdStyle}>
                            <div className="font-semibold truncate">{parent.description || '—'}</div>
                            <div className="font-bold text-ink-3" style={{ fontSize: 11 }}>
                                ORIGINAL{parentIsCurrent ? ' · VIEWING' : ''}
                            </div>
                        </td>
                        <td style={tdStyle}><StageChip stage={parent.stage} /></td>
                        <td style={tdStyle} className="text-ink-2 whitespace-nowrap">{parent.installer || <span className="italic text-ink-3">None</span>}</td>
                        <td style={numCell} className="text-ink-2">{cellHrs(own)}</td>
                        <td style={numCell} className="text-ink-2">0</td>
                    </tr>

                    {splices.length === 0 && (
                        <tr>
                            <td colSpan={6} style={tdStyle} className="text-jl-2 text-ink-3 italic">
                                No splices yet. Use + Splice to split install work off {releaseLabel(parent)}.
                            </td>
                        </tr>
                    )}

                    {splices.map((sp) => {
                        const isCurrent = sp.id === releaseId;
                        const extra = num(sp.additional_install_hrs) || 0;
                        return (
                            <React.Fragment key={sp.id}>
                                <tr {...rowProps(sp, isCurrent)}>
                                    <td style={tdStyle}><ReleaseLink row={sp} isCurrent={isCurrent} onOpen={onOpen} /></td>
                                    <td style={tdStyle}>
                                        <div className="font-semibold truncate">{sp.description || '—'}</div>
                                        {isCurrent && <div className="font-bold text-ink-3" style={{ fontSize: 11 }}>VIEWING</div>}
                                        {extra > 0 && sp.additional_install_note && (
                                            <div className="text-jl-2 text-ink-3 truncate">
                                                <span className="font-semibold">Why additional: </span>{sp.additional_install_note}
                                            </div>
                                        )}
                                        {sp.start_install && <div className="text-jl-2 text-ink-3">Start {sp.start_install}</div>}
                                    </td>
                                    <td style={tdStyle}><StageChip stage={sp.stage} /></td>
                                    <td style={tdStyle} className="text-ink-2 whitespace-nowrap">{sp.installer || <span className="italic text-ink-3">None</span>}</td>
                                    <td style={numCell} className="text-ink-2">{cellHrs(sp.budget_install_hrs ?? sp.install_hrs)}</td>
                                    <td style={numCell} className="text-ink-2">{cellHrs(extra)}</td>
                                </tr>
                            </React.Fragment>
                        );
                    })}
                </tbody>
                <tfoot>
                    <tr style={{ background: 'var(--surface-2)' }}>
                        <td style={{ ...tdStyle, borderTop: '2px solid var(--border-strong)' }} className="font-bold">Group</td>
                        <td style={{ ...tdStyle, borderTop: '2px solid var(--border-strong)' }} className="text-ink-3 whitespace-nowrap">
                            {rowCount} {rowCount === 1 ? 'release' : 'releases'}
                            {pool != null && additional > 0 ? ` · ${cellHrs(pool)} pool + ${cellHrs(additional)} additional` : ''}
                        </td>
                        <td style={{ ...tdStyle, borderTop: '2px solid var(--border-strong)' }} />
                        <td style={{ ...tdStyle, borderTop: '2px solid var(--border-strong)' }} />
                        <td style={{ ...numCell, borderTop: '2px solid var(--border-strong)' }} className="font-bold">{cellHrs(pool)}</td>
                        <td style={{ ...numCell, borderTop: '2px solid var(--border-strong)' }} className="font-bold">
                            {cellHrs(additional)}
                        </td>
                    </tr>
                </tfoot>
            </table>
        </div>
    );
}

/**
 * Side panel for one row of the group: Schedule, Details and to-dos, the same code as the
 * Details tab (JobDetailsBody, compact). Keyed by release id by the caller, so switching rows
 * starts clean.
 */
function ReleasePeek({ id, groupRow, isCurrent, onOpen, onClose, onChanged }) {
    const [row, setRow] = useState(null);
    const [error, setError] = useState(null);
    const [tick, setTick] = useState(0);

    useEffect(() => {
        let cancelled = false;
        setError(null);
        jobsApi.getRelease(id)
            .then((r) => {
                if (cancelled) return;
                if (!r) setError('That release no longer exists');
                setRow(r);
            })
            .catch((err) => { if (!cancelled) setError(err.message || 'Could not load release'); });
        return () => { cancelled = true; };
    }, [id, tick]);

    const label = groupRow ? releaseLabel(groupRow) : '';
    return (
        <div style={CARD} className="xl:max-h-[calc(100vh-220px)] xl:overflow-auto" data-testid="release-peek">
            <div
                className="flex items-start gap-3"
                style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', background: 'var(--surface-2)', borderRadius: '10px 10px 0 0' }}
            >
                <div className="min-w-0">
                    <div className="flex items-center flex-wrap gap-2">
                        <span className="font-bold whitespace-nowrap" style={{ color: 'var(--accent)', fontSize: 15 }}>{label}</span>
                        {groupRow && <StageChip stage={row?.Stage ?? row?.stage ?? groupRow.stage} />}
                    </div>
                    <div className="font-semibold text-ink truncate" style={{ marginTop: 2 }}>{groupRow?.description || '—'}</div>
                </div>
                <span className="flex-1" />
                {!isCurrent && onOpen && (
                    <button
                        type="button"
                        onClick={() => onOpen(id)}
                        className="bg-transparent border-0 p-0 font-semibold hover:underline cursor-pointer whitespace-nowrap"
                        style={{ fontSize: 12.5, color: 'var(--accent)', marginTop: 2 }}
                    >
                        Open
                    </button>
                )}
                <button
                    type="button"
                    onClick={onClose}
                    aria-label="Close details"
                    className="bg-transparent border-0 p-0 text-ink-3 hover:text-ink cursor-pointer"
                    style={{ fontSize: 18, lineHeight: 1 }}
                >
                    ×
                </button>
            </div>
            <div style={{ padding: '12px 16px 16px' }}>
                {error ? (
                    <p className="text-jl-2" style={{ color: 'var(--fl-red-fg)' }} role="alert">{error}</p>
                ) : !row ? (
                    <p className="text-jl-2 text-ink-3 italic">Loading…</p>
                ) : (
                    <JobDetailsBody
                        job={row}
                        releaseId={id}
                        compact
                        onJobUpdate={() => { setTick((t) => t + 1); onChanged?.(); }}
                    />
                )}
            </div>
        </div>
    );
}

export function SplicesPane({
    /** The release the hub is showing (releases.id). */
    releaseId,
    /** Opens another release of this group in the hub. */
    onOpenRelease = null,
    /** Host refetch after a splice is created. */
    onChanged = null,
    /** Reports the number of splices in the group (tab badge). */
    onCount = null,
}) {
    const [summary, setSummary] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [createOpen, setCreateOpen] = useState(false);
    const [selectedId, setSelectedId] = useState(null);
    useEffect(() => { setSelectedId(null); }, [releaseId]);

    const load = useCallback(async () => {
        if (releaseId == null) return;
        setLoading(true);
        setError(null);
        try {
            const data = await jobsApi.getSplices(releaseId);
            setSummary(data);
            onCount?.(data?.splices?.length || 0);
        } catch (err) {
            setError(err.message || 'Could not load splices');
        } finally {
            setLoading(false);
        }
    }, [releaseId, onCount]);

    useEffect(() => { load(); }, [load]);

    if (loading && !summary) {
        return <p className="text-jl-2 text-ink-3 italic">Loading splices…</p>;
    }
    if (error && !summary) {
        return <p className="text-jl-2" style={{ color: 'var(--fl-red-fg)' }}>{error}</p>;
    }
    if (!summary) return null;

    const parent = summary.parent || {
        id: summary.parent_id, job: summary.job, release: summary.release,
    };
    const splices = summary.splices || [];
    const pool = num(summary.total_install_hrs);
    const allocated = num(summary.allocated_install_hrs) || 0;
    // What the original still installs itself: the pool minus what splices drew. Read the
    // same number here as on the Job Log and Subs — never the gross.
    const own = pool == null ? null : (allocated > 0 ? num(summary.remaining_install_hrs) : pool);
    const additional = num(summary.additional_install_hrs) || 0;
    const groupTotal = num(summary.group_install_hrs);
    const parentLabel = releaseLabel(parent);
    const selectedRow = selectedId == null
        ? null
        : (parent.id === selectedId ? parent : splices.find((sp) => sp.id === selectedId)) || null;

    const headline = groupTotal == null
        ? `No install hours on ${parentLabel}`
        : `${fmtHrs(groupTotal)} hrs`;
    const subline = groupTotal == null
        ? 'Set install hours on the original first; budget hours draw from that pool.'
        : [
            splices.length === 0
                ? `on ${parentLabel}, nothing spliced off yet`
                : `across ${parentLabel} and its ${splices.length} ${splices.length === 1 ? 'splice' : 'splices'}`,
            pool != null && additional > 0 ? `${fmtHrs(pool)} from the budget pool, ${fmtHrs(additional)} additional` : null,
        ].filter(Boolean).join(' · ');

    return (
        <div className="grid gap-4 items-start xl:grid-cols-[minmax(0,1fr)_400px]">
            <div className="space-y-4 min-w-0">
                <div style={{ ...CARD, padding: '14px 18px 12px' }} className="space-y-3">
                    <div className="flex items-start flex-wrap gap-3">
                        <div className="min-w-0">
                            <div className={LABEL}>Install hours</div>
                            <div className="flex items-baseline flex-wrap gap-x-2" style={{ marginTop: 2 }}>
                                <span className="text-ink font-bold" style={{ fontSize: 26, lineHeight: 1.1 }}>{headline}</span>
                                <span className="text-ink-2" style={{ fontSize: 14 }}>{subline}</span>
                            </div>
                        </div>
                        <span className="flex-1" />
                        <button
                            type="button"
                            onClick={() => setCreateOpen(true)}
                            className="font-semibold border-0 cursor-pointer text-white whitespace-nowrap"
                            style={{ fontSize: 13, padding: '7px 14px', borderRadius: 7, background: 'var(--accent)' }}
                        >
                            + Splice
                        </button>
                    </div>
                    <HoursBar parent={parent} own={own} pool={pool} allocated={allocated} splices={splices} additional={additional} />
                    {hasManySplices(splices.length) && (
                        <div
                            role="note"
                            data-testid="many-splices-flag"
                            className="flex items-start gap-2 rounded-md text-jl-2"
                            style={{ padding: '8px 10px', background: 'var(--st-amber-bg)', color: 'var(--st-amber-fg)' }}
                        >
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className="shrink-0" style={{ marginTop: 1 }}>
                                <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" /><path d="M12 9v4" /><path d="M12 17h.01" />
                            </svg>
                            <span>
                                <span className="font-bold">{splices.length} splices on {parentLabel}.</span>{' '}
                                {MANY_SPLICES_THRESHOLD}+ splices on one release is a problem flag: check for cleanup or scope creep,
                                unless they are clarifying hold-downs by building.
                            </span>
                        </div>
                    )}
                </div>

                <GroupTable
                    parent={parent}
                    splices={splices}
                    releaseId={releaseId}
                    onOpen={onOpenRelease}
                    pool={pool}
                    own={own}
                    additional={additional}
                    selectedId={selectedId}
                    onSelect={setSelectedId}
                />
            </div>

            <aside className="min-w-0 xl:sticky xl:top-0">
                {selectedRow ? (
                    <ReleasePeek
                        key={selectedRow.id}
                        id={selectedRow.id}
                        groupRow={selectedRow}
                        isCurrent={selectedRow.id === releaseId}
                        onOpen={onOpenRelease}
                        onClose={() => setSelectedId(null)}
                        onChanged={() => { load(); onChanged?.(); }}
                    />
                ) : (
                    <p
                        className="hidden xl:block text-jl-2 text-ink-3 italic"
                        style={{ ...CARD, borderStyle: 'dashed', background: 'transparent', padding: '18px 16px' }}
                    >
                        Click a row to see its schedule, details and to-dos here.
                    </p>
                )}
            </aside>

            {createOpen && createPortal(
                <SpliceReleaseModal
                    isOpen={createOpen}
                    onClose={() => setCreateOpen(false)}
                    parentId={parent.id}
                    jobNumber={parent.job}
                    releaseNumber={parent.release}
                    jobName={parent.job_name}
                    description={parent.description}
                    releaseTag={parent.release_tag}
                    pool={summary}
                    onCreated={() => { load(); onChanged?.(); }}
                />,
                document.body,
            )}
        </div>
    );
}

export default SplicesPane;
