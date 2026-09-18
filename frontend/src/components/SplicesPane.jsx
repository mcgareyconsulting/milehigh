/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Splices tab of the release hub (roadmap T9) — the original release and every splice
 *   under it (340.1, 340.2 …) with the install-hour math laid out three ways: one continuous bar
 *   (Original | Splices | Additional, widths proportional to hours), a statement-style ledger, and
 *   a group table with a subtotal row. Each row opens that release in the same hub, mirror-card
 *   style, so you can move back and forth across the group.
 * exports:
 *   SplicesPane: Splices tab body for one release (original or splice)
 * imports_from: [react, react-dom, ../services/jobsApi, ../utils/stageTint, ./SpliceReleaseModal]
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
 *     So the table's Install column sums to pool + additional, never the gross.
 *   - The row being viewed is marked, not clickable; every other row calls onOpenRelease(id).
 *   - A splice's additional hours are editable in place (PATCH .../splice/additional-hours). Its
 *     recorded reason stays as it is; a reason is asked for only when the splice has none yet.
 * updated_by_agent: 2026-09-18T00:00:00Z
 */
import React, { useCallback, useEffect, useState } from 'react';
import { createPortal } from 'react-dom';

import { jobsApi } from '../services/jobsApi';
import { stageTint } from '../utils/stageTint';
import { SpliceReleaseModal } from './SpliceReleaseModal';

const fmtHrs = (v) => (v == null ? '—' : `${Number(v)}`);
const num = (v) => (v == null || v === '' ? null : (Number.isFinite(Number(v)) ? Number(v) : null));
const releaseLabel = (row) => `${row.job}-${row.release}`;

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

function AdditionalBadge({ hrs }) {
    return (
        <span
            className="inline-block font-semibold whitespace-nowrap"
            style={{ fontSize: 12, padding: '2px 8px', borderRadius: 999, background: 'var(--fl-amber-bg)', color: 'var(--fl-amber-fg)' }}
        >
            +{fmtHrs(hrs)}
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
            onClick={() => onOpen(row.id)}
            title={`Open ${label}`}
            className="bg-transparent border-0 p-0 font-bold whitespace-nowrap cursor-pointer hover:underline"
            style={{ color: 'var(--accent)', font: 'inherit', fontWeight: 700 }}
        >
            {label}
        </button>
    );
}

function AdditionalHoursEditor({ splice, onSaved, onCancel }) {
    const hasReason = !!(splice.additional_install_note || '').trim();
    const [hrs, setHrs] = useState(splice.additional_install_hrs != null ? String(splice.additional_install_hrs) : '');
    const [note, setNote] = useState('');
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState(null);

    const value = hrs === '' ? 0 : parseFloat(hrs);
    const valid = Number.isFinite(value) && value >= 0;
    const needsReason = valid && value > 0 && !hasReason;
    const canSave = valid && (!needsReason || note.trim() !== '') && !saving;

    const save = async (e) => {
        e?.preventDefault?.();
        if (!canSave) return;
        setSaving(true);
        setError(null);
        try {
            await jobsApi.updateSpliceAdditionalHours(splice.id, {
                additional_install_hrs: value,
                additional_install_note: needsReason ? note.trim() : null,
            });
            onSaved?.();
        } catch (err) {
            setError(err.message || 'Could not update additional hours');
            setSaving(false);
        }
    };

    const inputStyle = { fontSize: 13, padding: '5px 8px', borderColor: 'var(--border)' };
    return (
        <form onSubmit={save} className="space-y-2">
            <div className="flex items-center flex-wrap gap-2">
                <label htmlFor={`addl-${splice.id}`} className="text-jl-2 text-ink-2 font-semibold">
                    Additional install hours for {releaseLabel(splice)}
                </label>
                <input
                    id={`addl-${splice.id}`}
                    type="number"
                    inputMode="decimal"
                    min="0"
                    step="0.5"
                    value={hrs}
                    onChange={(e) => setHrs(e.target.value)}
                    autoFocus
                    className="text-ink bg-surface border rounded-md"
                    style={{ ...inputStyle, width: 90 }}
                />
                <button
                    type="submit"
                    disabled={!canSave}
                    className="font-semibold border-0 text-white rounded-[7px] disabled:opacity-50"
                    style={{ fontSize: 12.5, padding: '5px 11px', background: 'var(--accent)' }}
                >
                    {saving ? 'Saving…' : 'Save'}
                </button>
                <button
                    type="button"
                    onClick={onCancel}
                    className="text-ink-2 bg-transparent border-0 font-medium"
                    style={{ fontSize: 12.5, padding: '5px 6px' }}
                >
                    Cancel
                </button>
            </div>
            {needsReason && (
                <textarea
                    rows={2}
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    className="w-full text-ink bg-surface border rounded-md resize-y"
                    style={inputStyle}
                    placeholder="Why are additional hours needed? (required)"
                    aria-label="Why are additional hours needed?"
                />
            )}
            <p className="text-jl-2 text-ink-3">
                Budget hours stay at {fmtHrs(splice.budget_install_hrs ?? splice.install_hrs)}; the total becomes {fmtHrs((Number(splice.budget_install_hrs ?? splice.install_hrs) || 0) + (valid ? value : 0))}.
            </p>
            {error && <p className="text-jl-2" style={{ color: 'var(--fl-red-fg)' }} role="alert">{error}</p>}
        </form>
    );
}

/**
 * One continuous bar: Original | Splices (one slice per splice that drew budget hours) |
 * Additional. Widths are the hours themselves as flex weights, so 2 : 10 : 14 of 26 reads as
 * such. A 3px gap separates the three kinds, 1px separates splices from each other. The
 * legend under it carries the words, so a segment too thin to hold its number still reads.
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
        boxSizing: 'border-box',
        ...extra,
    });
    const parentLabel = releaseLabel(parent);
    const swatch = (style) => (
        <span aria-hidden="true" className="inline-block shrink-0" style={{ width: 10, height: 10, borderRadius: 2, boxSizing: 'border-box', ...style }} />
    );

    return (
        <div className="space-y-2" data-testid="hours-bar">
            <div role="img" aria-label={`Install hours: ${fmtHrs(ownHrs)} left on ${parentLabel}, ${fmtHrs(allocated)} spliced off, ${fmtHrs(additional)} additional`}
                style={{ display: 'flex', gap: 3, height: 32, borderRadius: 6, overflow: 'hidden' }}>
                {ownHrs > 0 && (
                    <div
                        title={`${parentLabel} still installs ${fmtHrs(ownHrs)} hrs itself`}
                        style={seg(ownHrs, { background: 'var(--accent-soft)', border: '1px solid var(--accent)', color: 'var(--accent)' })}
                    >
                        {fmtHrs(ownHrs)}
                    </div>
                )}
                {allocated > 0 && (
                    <div style={{ flex: `${allocated} 1 0%`, minWidth: 0, display: 'flex', gap: 1 }}>
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
                        style={seg(additional, { background: 'var(--fl-amber-bg)', color: 'var(--fl-amber-fg)' })}
                    >
                        +{fmtHrs(additional)}
                    </div>
                )}
            </div>

            <div className="flex flex-wrap gap-x-5 gap-y-1 text-jl-2 text-ink-2">
                <span className="flex items-center gap-1.5">
                    {swatch({ background: 'var(--accent-soft)', border: '1px solid var(--accent)' })}
                    <span className="font-semibold text-ink">Original</span>
                    <span>
                        {pool == null
                            ? 'no install hours yet'
                            : allocated > 0
                                ? `${fmtHrs(ownHrs)} hrs left of a ${fmtHrs(pool)} hr pool`
                                : `${fmtHrs(pool)} hrs, none spliced off`}
                    </span>
                </span>
                {splices.length > 0 && (
                    <span className="flex items-center gap-1.5">
                        {swatch({ background: 'var(--accent)' })}
                        <span className="font-semibold text-ink">Splices</span>
                        <span>{fmtHrs(allocated)} hrs from the pool</span>
                        <span className="text-ink-3">
                            {splices.map((sp) => `${releaseLabel(sp)} ${fmtHrs(sp.budget_install_hrs ?? sp.install_hrs)}`).join(' · ')}
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

function LedgerLine({ label, value, indent = false, strong = false, dotted = true, style = {} }) {
    return (
        <div className="flex items-baseline gap-2.5" style={{ padding: '4px 0', paddingLeft: indent ? 16 : 0, ...style }}>
            <span className={`min-w-0 whitespace-nowrap ${strong ? 'font-bold text-ink' : 'text-ink-2'}`}>{label}</span>
            <span className="flex-1" style={dotted ? { borderBottom: '1px dotted var(--border-strong)', transform: 'translateY(-4px)' } : undefined} />
            <span className={`text-right whitespace-nowrap ${strong ? 'font-bold text-ink' : 'text-ink-2'}`} style={{ width: 56 }}>{value}</span>
        </div>
    );
}

/** Pool − each splice = left on the original; + additional = group total. */
function HoursLedger({ parent, pool, own, splices, groupTotal }) {
    const parentLabel = releaseLabel(parent);
    const extras = splices.filter((sp) => (num(sp.additional_install_hrs) || 0) > 0);
    return (
        <div className="text-jl" style={{ ...CARD, background: 'var(--surface-2)', padding: '14px 18px 12px' }} data-testid="hours-ledger">
            <div className={LABEL} style={{ paddingBottom: 6 }}>Hours math</div>

            {pool == null ? (
                <p className="text-jl-2 text-ink-3 italic" style={{ padding: '4px 0' }}>
                    No install hours on {parentLabel} yet, so there is no pool to splice from.
                </p>
            ) : (
                <>
                    <LedgerLine
                        label={<>Budget pool on <span className="font-bold text-ink">{parentLabel}</span></>}
                        value={<span className="font-bold text-ink">{fmtHrs(pool)}</span>}
                    />
                    {splices.map((sp) => (
                        <LedgerLine
                            key={sp.id}
                            indent
                            label={<><span className="font-bold" style={{ color: 'var(--accent)' }}>{releaseLabel(sp)}</span> {sp.description || ''}</>}
                            value={`− ${fmtHrs(sp.budget_install_hrs ?? sp.install_hrs)}`}
                        />
                    ))}
                    <LedgerLine
                        strong
                        dotted={false}
                        label={`Left on ${parentLabel}`}
                        value={fmtHrs(own)}
                        style={{ marginTop: 2, borderTop: '1px solid var(--border-strong)', padding: '7px 0 5px' }}
                    />
                </>
            )}

            {extras.length > 0 && (
                <>
                    <div className="text-ink-2" style={{ padding: '6px 0 2px' }}>Additional, outside the pool</div>
                    {extras.map((sp) => (
                        <LedgerLine
                            key={sp.id}
                            indent
                            label={<><span className="font-bold" style={{ color: 'var(--accent)' }}>{releaseLabel(sp)}</span> <span className="text-ink-3">{sp.additional_install_note ? `“${sp.additional_install_note}”` : ''}</span></>}
                            value={<span className="font-bold" style={{ color: 'var(--st-amber-fg)' }}>+ {fmtHrs(sp.additional_install_hrs)}</span>}
                        />
                    ))}
                </>
            )}

            {groupTotal != null && (
                <div className="flex items-baseline gap-2.5" style={{ marginTop: 4, padding: '8px 0 2px', borderTop: '2px solid var(--text)' }}>
                    <span className="font-bold text-ink" style={{ fontSize: 15 }}>Group total install hrs</span>
                    <span className="flex-1" />
                    <span className="font-bold text-ink text-right" style={{ fontSize: 18, width: 56 }}>{fmtHrs(groupTotal)}</span>
                </div>
            )}
        </div>
    );
}

const TH = 'text-left font-bold uppercase text-ink-3 whitespace-nowrap';
const thStyle = { fontSize: 11.5, letterSpacing: '.05em', padding: '8px 10px', background: 'var(--head-bg)' };
const tdStyle = { padding: '10px 10px', verticalAlign: 'middle', borderTop: '1px solid var(--border)' };
const numCell = { ...tdStyle, textAlign: 'right', whiteSpace: 'nowrap' };

/** The group as a table: one row per release, subtotal at the foot, every column adds up. */
function GroupTable({
    parent, splices, releaseId, onOpen, pool, own, allocated, additional, groupTotal,
    editingId, onEdit, onCancelEdit, onSaved,
}) {
    const parentIsCurrent = parent.id === releaseId;
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
                        <th scope="col" className={TH} style={{ ...thStyle, textAlign: 'right' }}>Budget</th>
                        <th scope="col" className={TH} style={{ ...thStyle, textAlign: 'right' }}>Additional</th>
                        <th scope="col" className={TH} style={{ ...thStyle, textAlign: 'right' }}>Install</th>
                        <th scope="col" className={TH} style={{ ...thStyle, textAlign: 'right' }}>Fab</th>
                    </tr>
                </thead>
                <tbody>
                    <tr
                        aria-current={parentIsCurrent ? 'true' : undefined}
                        style={parentIsCurrent ? { background: 'var(--accent-soft)', boxShadow: 'inset 3px 0 0 var(--accent)' } : undefined}
                    >
                        <td style={tdStyle}><ReleaseLink row={parent} isCurrent={parentIsCurrent} onOpen={onOpen} /></td>
                        <td style={tdStyle}>
                            <div className="font-semibold truncate">{parent.description || '—'}</div>
                            <div className="font-bold text-ink-3" style={{ fontSize: 11 }}>
                                ORIGINAL{parentIsCurrent ? ' · VIEWING' : ''}
                            </div>
                        </td>
                        <td style={tdStyle}><StageChip stage={parent.stage} /></td>
                        <td style={tdStyle} className="text-ink-2 whitespace-nowrap">{parent.installer || <span className="italic text-ink-3">None</span>}</td>
                        <td style={numCell} className="text-ink-2">
                            {pool == null ? '—' : allocated > 0 ? <><span className="font-bold text-ink">{fmtHrs(own)}</span> of {fmtHrs(pool)}</> : fmtHrs(pool)}
                        </td>
                        <td style={numCell} className="text-ink-3">—</td>
                        <td style={numCell} className="font-bold">{fmtHrs(own)}</td>
                        <td style={numCell} className="text-ink-2">{fmtHrs(parent.fab_hrs)}</td>
                    </tr>

                    {splices.length === 0 && (
                        <tr>
                            <td colSpan={8} style={tdStyle} className="text-jl-2 text-ink-3 italic">
                                No splices yet. Use + Splice to split install work off {releaseLabel(parent)}.
                            </td>
                        </tr>
                    )}

                    {splices.map((sp) => {
                        const isCurrent = sp.id === releaseId;
                        const extra = num(sp.additional_install_hrs) || 0;
                        const editing = editingId === sp.id;
                        return (
                            <React.Fragment key={sp.id}>
                                <tr
                                    aria-current={isCurrent ? 'true' : undefined}
                                    style={isCurrent ? { background: 'var(--accent-soft)', boxShadow: 'inset 3px 0 0 var(--accent)' } : undefined}
                                >
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
                                    <td style={numCell} className="text-ink-2">{fmtHrs(sp.budget_install_hrs ?? sp.install_hrs)}</td>
                                    <td style={numCell}>
                                        <span className="inline-flex items-center gap-2 justify-end">
                                            {extra > 0 ? <AdditionalBadge hrs={extra} /> : null}
                                            {!editing && (
                                                <button
                                                    type="button"
                                                    onClick={() => onEdit(sp.id)}
                                                    className="bg-transparent border-0 p-0 font-semibold hover:underline cursor-pointer"
                                                    style={{ fontSize: 12.5, color: 'var(--accent)' }}
                                                    aria-label={extra > 0 ? `Edit additional hours for ${releaseLabel(sp)}` : `Add additional hours to ${releaseLabel(sp)}`}
                                                >
                                                    {extra > 0 ? 'Edit' : '+ Add'}
                                                </button>
                                            )}
                                        </span>
                                    </td>
                                    <td style={numCell} className="font-bold">{fmtHrs(sp.install_hrs)}</td>
                                    <td style={numCell} className="text-ink-3">—</td>
                                </tr>
                                {editing && (
                                    <tr>
                                        <td colSpan={8} style={{ ...tdStyle, borderTop: 0, paddingTop: 0, background: 'var(--surface-2)' }}>
                                            <AdditionalHoursEditor splice={sp} onCancel={onCancelEdit} onSaved={onSaved} />
                                        </td>
                                    </tr>
                                )}
                            </React.Fragment>
                        );
                    })}
                </tbody>
                <tfoot>
                    <tr style={{ background: 'var(--surface-2)' }}>
                        <td style={{ ...tdStyle, borderTop: '2px solid var(--border-strong)' }} className="font-bold">Group</td>
                        <td style={{ ...tdStyle, borderTop: '2px solid var(--border-strong)' }} className="text-ink-3 whitespace-nowrap">
                            {rowCount} {rowCount === 1 ? 'release' : 'releases'}
                            {pool != null && additional > 0 ? ` · ${fmtHrs(pool)} pool + ${fmtHrs(additional)} additional` : ''}
                        </td>
                        <td style={{ ...tdStyle, borderTop: '2px solid var(--border-strong)' }} />
                        <td style={{ ...tdStyle, borderTop: '2px solid var(--border-strong)' }} />
                        <td style={{ ...numCell, borderTop: '2px solid var(--border-strong)' }} className="font-bold">{fmtHrs(pool)}</td>
                        <td style={{ ...numCell, borderTop: '2px solid var(--border-strong)' }} className="font-bold">
                            {additional > 0 ? <span style={{ color: 'var(--st-amber-fg)' }}>+{fmtHrs(additional)}</span> : '—'}
                        </td>
                        <td style={{ ...numCell, borderTop: '2px solid var(--border-strong)', fontSize: 16 }} className="font-bold">{fmtHrs(groupTotal)}</td>
                        <td style={{ ...numCell, borderTop: '2px solid var(--border-strong)' }} className="font-bold">{fmtHrs(parent.fab_hrs)}</td>
                    </tr>
                </tfoot>
            </table>
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
    const [editingId, setEditingId] = useState(null);

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

    const editorHandlers = {
        editingId,
        onEdit: setEditingId,
        onCancelEdit: () => setEditingId(null),
        onSaved: () => { setEditingId(null); load(); onChanged?.(); },
    };

    return (
        <div className="space-y-4" style={{ maxWidth: 1180 }}>
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
            </div>

            <div className="grid gap-4 items-start lg:grid-cols-[340px_minmax(0,1fr)]">
                <HoursLedger parent={parent} pool={pool} own={own} splices={splices} groupTotal={groupTotal} />
                <GroupTable
                    parent={parent}
                    splices={splices}
                    releaseId={releaseId}
                    onOpen={onOpenRelease}
                    pool={pool}
                    own={own}
                    allocated={allocated}
                    additional={additional}
                    groupTotal={groupTotal}
                    {...editorHandlers}
                />
            </div>

            <p className="text-jl-2 text-ink-3">
                Budget = hours drawn from the original’s pool. Additional = hours outside the pool, always with a reason.
                Install = budget + additional; the original shows what it still installs itself.
            </p>

            {createOpen && createPortal(
                <SpliceReleaseModal
                    isOpen={createOpen}
                    onClose={() => setCreateOpen(false)}
                    parentId={parent.id}
                    jobNumber={parent.job}
                    releaseNumber={parent.release}
                    jobName={parent.job_name}
                    description={parent.description}
                    pool={summary}
                    onCreated={() => { load(); onChanged?.(); }}
                />,
                document.body,
            )}
        </div>
    );
}

export default SplicesPane;
