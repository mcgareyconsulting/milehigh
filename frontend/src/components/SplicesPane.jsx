/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Splices tab of the release hub (roadmap T9) — the original release and every splice
 *   under it (340.1, 340.2 …), the budget install-hour pool, and + Splice. Each row opens that
 *   release in the same hub, mirror-card style, so you can move back and forth across the group.
 * exports:
 *   SplicesPane: Splices tab body for one release (original or splice)
 * imports_from: [react, react-dom, ../services/jobsApi, ../utils/stageTint, ./SpliceReleaseModal]
 * imported_by: [frontend/src/components/ReleaseHubModal.jsx]
 * invariants:
 *   - Spec: Bill, 2026-09-16 shop session. Replaces the Splices section that sat buried in Details.
 *   - GET /splices answers for the ORIGINAL whether this row is the original or a splice, so the
 *     pane reads the same from either side; + Splice always creates under the original.
 *   - Pool numbers are BUDGET hours. Additional hours sit outside the pool and are flagged per splice
 *     with their reason.
 *   - The original's line shows what it still installs ITSELF (pool minus spliced), the same number the
 *     Job Log and Subs → Invoice Paid show for it — its stored install_hrs stays the whole pool.
 *   - The row being viewed is marked, not clickable; every other row calls onOpenRelease(id).
 *   - A splice's additional hours are editable in place (PATCH .../splice/additional-hours). Its
 *     recorded reason stays as it is; a reason is asked for only when the splice has none yet.
 * updated_by_agent: 2026-09-16T00:00:00Z
 */
import React, { useCallback, useEffect, useState } from 'react';
import { createPortal } from 'react-dom';

import { jobsApi } from '../services/jobsApi';
import { stageTint } from '../utils/stageTint';
import { SpliceReleaseModal } from './SpliceReleaseModal';

const fmtHrs = (v) => (v == null ? '—' : `${Number(v)}`);

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

function GroupRow({ row, isCurrent, onOpen, badge = null, children = null }) {
    const clickable = !isCurrent && onOpen;
    const Head = clickable ? 'button' : 'div';
    return (
        <div
            className="border rounded-lg"
            style={{
                padding: '10px 12px',
                borderColor: isCurrent ? 'var(--accent)' : 'var(--border)',
                background: isCurrent ? 'var(--accent-soft)' : undefined,
            }}
            aria-current={isCurrent ? 'true' : undefined}
        >
            <Head
                type={clickable ? 'button' : undefined}
                onClick={clickable ? () => onOpen(row.id) : undefined}
                className={`w-full text-left bg-transparent border-0 p-0 flex items-center flex-wrap gap-x-2.5 gap-y-1 ${clickable ? 'cursor-pointer hover:underline' : ''}`}
                title={clickable ? `Open ${row.job}-${row.release}` : undefined}
            >
                <span className="font-mono font-bold" style={{ fontSize: 13.5, color: 'var(--accent)' }}>
                    {row.job}-{row.release}
                </span>
                {badge}
                <span className="text-ink truncate min-w-0" style={{ fontSize: 13.5, fontWeight: 600 }}>
                    {row.description || '—'}
                </span>
                <span className="flex-1" />
                <StageChip stage={row.stage} />
                {isCurrent ? (
                    <span className="text-ink-3 font-semibold" style={{ fontSize: 11.5 }}>Viewing</span>
                ) : (
                    <span className="text-ink-3" aria-hidden="true" style={{ fontSize: 14 }}>›</span>
                )}
            </Head>
            {children}
        </div>
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
        <form onSubmit={save} className="space-y-2" style={{ marginTop: 8 }}>
            <div className="flex items-center flex-wrap gap-2">
                <label htmlFor={`addl-${splice.id}`} className="text-jl-2 text-ink-2 font-semibold">Additional install hours</label>
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
    const total = summary.total_install_hrs;
    const allocated = Number(summary.allocated_install_hrs) || 0;

    return (
        <div className="space-y-4" style={{ maxWidth: 820 }}>
            <div className="flex items-start flex-wrap gap-3">
                <div className="min-w-0">
                    <div className="text-jl-label font-bold uppercase text-ink-3">Budget install hours</div>
                    <div className="text-ink" style={{ fontSize: 15, fontWeight: 600, marginTop: 2 }}>
                        {total == null
                            ? `No install hours on ${parent.job}-${parent.release}`
                            : `${fmtHrs(summary.remaining_install_hrs)} of ${fmtHrs(total)} hrs remaining`}
                    </div>
                    {total != null && (
                        <div className="text-jl-2 text-ink-3" style={{ marginTop: 2 }}>
                            {`${fmtHrs(summary.allocated_install_hrs)} hrs spliced from ${parent.job}-${parent.release}`}
                        </div>
                    )}
                </div>
                <span className="flex-1" />
                <button
                    type="button"
                    onClick={() => setCreateOpen(true)}
                    className="font-semibold border-0 cursor-pointer text-white"
                    style={{ fontSize: 13, padding: '7px 14px', borderRadius: 7, background: 'var(--accent)' }}
                >
                    + Splice
                </button>
            </div>

            <div>
                <div className="text-jl-label font-bold uppercase text-ink-3" style={{ marginBottom: 6 }}>Original</div>
                <GroupRow row={parent} isCurrent={parent.id === releaseId} onOpen={onOpenRelease}>
                    <div className="text-jl-2 text-ink-3" style={{ marginTop: 4 }}>
                        {[
                            parent.installer ? `Installer ${parent.installer}` : null,
                            // The original's install hours are the whole pool; what it still
                            // installs itself is the pool minus what these splices drew. Read
                            // the same number here as on the Job Log and Subs — never the gross.
                            parent.install_hrs != null
                                ? (allocated > 0
                                    ? `${fmtHrs(summary.remaining_install_hrs)} install hrs left of ${fmtHrs(parent.install_hrs)}`
                                    : `${fmtHrs(parent.install_hrs)} install hrs`)
                                : null,
                            parent.fab_hrs != null ? `${fmtHrs(parent.fab_hrs)} fab hrs` : null,
                        ].filter(Boolean).join(' · ') || '—'}
                    </div>
                </GroupRow>
            </div>

            <div>
                <div className="text-jl-label font-bold uppercase text-ink-3" style={{ marginBottom: 6 }}>
                    Splices{splices.length ? ` · ${splices.length}` : ''}
                </div>
                {splices.length === 0 ? (
                    <p className="text-jl-2 text-ink-3 italic" style={{ padding: '6px 2px' }}>
                        No splices yet. Use + Splice to split install work off {parent.job}-{parent.release}.
                    </p>
                ) : (
                    <div className="space-y-2">
                        {splices.map((sp) => {
                            const extra = Number(sp.additional_install_hrs) || 0;
                            return (
                                <GroupRow
                                    key={sp.id}
                                    row={sp}
                                    isCurrent={sp.id === releaseId}
                                    onOpen={onOpenRelease}
                                    badge={extra > 0 ? (
                                        <span
                                            className="inline-block font-semibold whitespace-nowrap"
                                            style={{ fontSize: 11.5, padding: '2px 8px', borderRadius: 999, background: 'var(--fl-amber-bg)', color: 'var(--fl-amber-fg)' }}
                                        >
                                            +{fmtHrs(extra)} additional
                                        </span>
                                    ) : null}
                                >
                                    <div className="text-jl-2 text-ink-3" style={{ marginTop: 4 }}>
                                        {[
                                            sp.installer ? `Installer ${sp.installer}` : 'No installer',
                                            `${fmtHrs(sp.budget_install_hrs ?? sp.install_hrs)} budget hrs`,
                                            extra > 0 ? `${fmtHrs(sp.install_hrs)} total` : null,
                                            sp.start_install ? `Start ${sp.start_install}` : null,
                                        ].filter(Boolean).join(' · ')}
                                    </div>
                                    {extra > 0 && sp.additional_install_note && (
                                        <div className="text-jl-2 text-ink-2" style={{ marginTop: 4 }}>
                                            <span className="font-semibold">Why additional: </span>
                                            {sp.additional_install_note}
                                        </div>
                                    )}
                                    {editingId === sp.id ? (
                                        <AdditionalHoursEditor
                                            splice={sp}
                                            onCancel={() => setEditingId(null)}
                                            onSaved={() => { setEditingId(null); load(); onChanged?.(); }}
                                        />
                                    ) : (
                                        <button
                                            type="button"
                                            onClick={() => setEditingId(sp.id)}
                                            className="bg-transparent border-0 p-0 font-semibold hover:underline"
                                            style={{ fontSize: 12.5, marginTop: 6, color: 'var(--accent)' }}
                                        >
                                            {extra > 0 ? 'Edit additional hours' : '+ Additional hours'}
                                        </button>
                                    )}
                                </GroupRow>
                            );
                        })}
                    </div>
                )}
            </div>

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
