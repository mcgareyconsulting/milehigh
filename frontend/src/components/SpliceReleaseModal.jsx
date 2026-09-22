/**
 * @milehigh-header
 * schema_version: 1
 * purpose: "+ Splice" dialog — creates a 340.1 / 340.2 child release under an original release.
 *   The original's number, name and description are shown read-only; the user writes the splice's
 *   own description, picks stage, installer and an optional start install date, and gives budget
 *   install hours (drawn from the original's pool) and/or additional install hours (outside the
 *   pool, with a required reason). No fab hours, no Trello.
 * exports:
 *   SpliceReleaseModal: Portal-free dialog (the caller portals it)
 * imports_from: [react, ../services/jobsApi, ../constants/stages]
 * imported_by: [frontend/src/components/SplicesPane.jsx]
 * invariants:
 *   - Spec: Bill, 2026-09-16 shop session (roadmap T9).
 *   - Description is required and must differ from the original's (whitespace/case-insensitive);
 *     an installer is required only when the splice carries install hours. The server enforces
 *     both — a 400/409 is surfaced verbatim.
 *   - Budget install hours are capped at the pool's remaining hours client-side AND server-side.
 *   - Additional install hours need a note. Budget 0 + additional 0 is a ZERO-HOUR splice (drop
 *     ship, material only — training handout 2026-09-21), legal with no installer; the form says
 *     so instead of blocking.
 *   - The release number is display-only; it is never sent.
 * updated_by_agent: 2026-09-22T00:00:00Z
 */
import React, { useEffect, useState } from 'react';
import { jobsApi } from '../services/jobsApi';
import { STAGE_OPTIONS } from '../constants/stages';

const todayYmd = () => {
    const d = new Date();
    const m = `${d.getMonth() + 1}`.padStart(2, '0');
    const day = `${d.getDate()}`.padStart(2, '0');
    return `${d.getFullYear()}-${m}-${day}`;
};

const fmtHrs = (v) => (v == null ? '—' : `${Number(v)}`);
const normText = (v) => String(v ?? '').split(/\s+/).filter(Boolean).join(' ').toLowerCase();

const inputCls = 'w-full text-ink bg-surface border rounded-md focus:outline-none';
const inputStyle = { fontSize: 13.5, padding: '7px 9px' };

function FieldLabel({ htmlFor, children, required = false }) {
    return (
        <label htmlFor={htmlFor} className="block text-jl-label font-bold uppercase text-ink-3" style={{ marginBottom: 4 }}>
            {children}{required && <span style={{ color: 'var(--fl-red-fg)' }}> *</span>}
        </label>
    );
}

function ReadOnly({ label, children, mono = false }) {
    return (
        <div className="min-w-0">
            <span className="block text-jl-label font-bold uppercase text-ink-3" style={{ marginBottom: 4 }}>{label}</span>
            <div
                className={`text-ink-2 bg-surface-2 border border-hairline rounded-md truncate ${mono ? 'font-mono' : ''}`}
                style={inputStyle}
                title={typeof children === 'string' ? children : undefined}
            >
                {children || '—'}
            </div>
        </div>
    );
}

export function SpliceReleaseModal({
    isOpen,
    onClose,
    /** Original (parent) row id (releases.id). */
    parentId,
    jobNumber,
    releaseNumber,
    jobName = '',
    description = '',
    /** Pool snapshot from GET /splices; refreshed on open. */
    pool = null,
    /** Called with the server response after a successful create. */
    onCreated = null,
}) {
    const [livePool, setLivePool] = useState(pool);
    const [installerOptions, setInstallerOptions] = useState([]);
    const [desc, setDesc] = useState('');
    const [stage, setStage] = useState('Released');
    const [installer, setInstaller] = useState('');
    const [startInstall, setStartInstall] = useState('');
    const [budgetHrs, setBudgetHrs] = useState('');
    const [additionalOn, setAdditionalOn] = useState(false);
    const [additionalHrs, setAdditionalHrs] = useState('');
    const [additionalNote, setAdditionalNote] = useState('');
    const [released, setReleased] = useState(todayYmd());
    const [submitting, setSubmitting] = useState(false);
    const [error, setError] = useState(null);

    useEffect(() => {
        if (!isOpen) return undefined;
        setDesc('');
        setStage('Released');
        setInstaller('');
        setStartInstall('');
        setBudgetHrs('');
        setAdditionalOn(false);
        setAdditionalHrs('');
        setAdditionalNote('');
        setReleased(todayYmd());
        setError(null);
        setLivePool(pool);
        let cancelled = false;
        if (parentId != null) {
            jobsApi.getSplices(parentId)
                .then((data) => { if (!cancelled) setLivePool(data); })
                .catch(() => { /* keep the snapshot we were handed */ });
        }
        jobsApi.getInstallerTeams()
            .then((teams) => { if (!cancelled) setInstallerOptions(teams || []); })
            .catch(() => { if (!cancelled) setInstallerOptions([]); });
        return () => { cancelled = true; };
    }, [isOpen, parentId, pool]);

    useEffect(() => {
        if (!isOpen) return undefined;
        const onKey = (e) => {
            if (e.key !== 'Escape') return;
            // The hub listens for Escape too — claim it so only this dialog closes.
            e.stopImmediatePropagation();
            onClose?.();
        };
        window.addEventListener('keydown', onKey, true);
        return () => window.removeEventListener('keydown', onKey, true);
    }, [isOpen, onClose]);

    if (!isOpen) return null;

    const remaining = livePool?.remaining_install_hrs;
    const total = livePool?.total_install_hrs;
    const noPool = total == null;
    const nextNumber = livePool?.next_splice_number || `${releaseNumber}.?`;

    const descTrim = desc.trim();
    const descSame = descTrim !== '' && normText(descTrim) === normText(description);
    const descValid = descTrim !== '' && !descSame;

    const budget = budgetHrs === '' ? 0 : parseFloat(budgetHrs);
    const budgetValid = Number.isFinite(budget) && budget >= 0;
    const overPool = budgetValid && budget > 0 && remaining != null && budget > remaining + 1e-9;
    const budgetNeedsPool = budgetValid && budget > 0 && noPool;

    const extra = additionalOn && additionalHrs !== '' ? parseFloat(additionalHrs) : 0;
    const extraValid = !additionalOn || (Number.isFinite(extra) && extra > 0);
    const noteValid = !additionalOn || additionalNote.trim() !== '';
    const totalHrs = (budgetValid ? budget : 0) + (additionalOn && Number.isFinite(extra) ? extra : 0);
    // No hours at all is a zero-hour splice (drop ship, material only): legal, and it needs no
    // installer since there is nothing to install.
    const zeroHour = budgetValid && extraValid && totalHrs === 0;
    const installerOk = installer !== '' || zeroHour;

    const canSubmit = descValid && installerOk && budgetValid && !overPool && !budgetNeedsPool
        && extraValid && noteValid && !submitting;

    const submit = async (e) => {
        e?.preventDefault?.();
        if (!canSubmit) return;
        setSubmitting(true);
        setError(null);
        try {
            const result = await jobsApi.createSplice(parentId, {
                description: descTrim,
                installer: installer || null,
                stage,
                start_install: startInstall || null,
                install_hrs: budget > 0 ? budget : null,
                additional_install_hrs: additionalOn ? extra : null,
                additional_install_note: additionalOn ? additionalNote.trim() : null,
                released: released || null,
            });
            onCreated?.(result);
            onClose?.();
        } catch (err) {
            setError(err.message || 'Could not create the splice');
        } finally {
            setSubmitting(false);
        }
    };

    const border = (bad) => ({ ...inputStyle, borderColor: bad ? 'var(--fl-red-fg)' : 'var(--border)' });

    return (
        <div
            className="fixed inset-0 z-[60] flex items-center justify-center p-3"
            style={{ background: 'rgba(10,16,28,.55)' }}
            onClick={onClose}
        >
            <form
                onSubmit={submit}
                onClick={(e) => e.stopPropagation()}
                className="bg-surface border border-hairline-strong w-full flex flex-col overflow-hidden"
                style={{ maxWidth: 560, maxHeight: 'calc(100dvh - 24px)', borderRadius: 14, boxShadow: 'var(--shadow)' }}
                role="dialog"
                aria-modal="true"
                aria-label="Splice release"
            >
                <div className="shrink-0 border-b border-hairline bg-surface-2 flex items-center justify-between" style={{ padding: '12px 18px' }}>
                    <div className="min-w-0">
                        <div className="text-ink font-bold" style={{ fontSize: 17 }}>Splice release</div>
                        <div className="text-ink-3" style={{ fontSize: 12.5 }}>
                            Creates <span className="font-mono">{jobNumber}-{nextNumber}</span> · no fab hours, no Trello card
                        </div>
                    </div>
                    <button
                        type="button"
                        onClick={onClose}
                        className="grid place-items-center border border-hairline-strong rounded-[7px] bg-surface text-ink-2 hover:text-ink"
                        style={{ width: 28, height: 28 }}
                        aria-label="Close"
                    >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
                            <path d="M6 6l12 12 M18 6L6 18" />
                        </svg>
                    </button>
                </div>

                <div className="flex-1 min-h-0 overflow-auto space-y-4" style={{ padding: '16px 18px' }}>
                    <div>
                        <div className="text-jl-label font-bold uppercase text-ink-3" style={{ marginBottom: 6 }}>Original</div>
                        <div className="grid gap-2" style={{ gridTemplateColumns: 'minmax(0,110px) minmax(0,1fr)' }}>
                            <ReadOnly label="Job-release" mono>{`${jobNumber}-${releaseNumber}`}</ReadOnly>
                            <ReadOnly label="Job name">{jobName}</ReadOnly>
                        </div>
                        <div style={{ marginTop: 8 }}>
                            <ReadOnly label="Description">{description}</ReadOnly>
                        </div>
                    </div>

                    <div>
                        <FieldLabel htmlFor="splice-description" required>New description</FieldLabel>
                        <input
                            id="splice-description"
                            type="text"
                            maxLength={256}
                            value={desc}
                            onChange={(e) => setDesc(e.target.value)}
                            autoFocus
                            className={inputCls}
                            style={border(descSame)}
                            placeholder="What this splice covers (e.g. wall handrails only)"
                        />
                        {descSame && (
                            <p className="text-jl-2 mt-1" style={{ color: 'var(--fl-red-fg)' }}>
                                Must differ from the original's description.
                            </p>
                        )}
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <div>
                            <FieldLabel htmlFor="splice-stage">Stage</FieldLabel>
                            <select id="splice-stage" value={stage} onChange={(e) => setStage(e.target.value)} className={inputCls} style={border(false)}>
                                {STAGE_OPTIONS.map((o) => (
                                    <option key={o.value} value={o.value}>{o.value}</option>
                                ))}
                            </select>
                        </div>
                        <div>
                            <FieldLabel htmlFor="splice-installer" required={!zeroHour}>Installer</FieldLabel>
                            <select id="splice-installer" value={installer} onChange={(e) => setInstaller(e.target.value)} className={inputCls} style={border(false)}>
                                <option value="">Select installer…</option>
                                {installerOptions.map((t) => {
                                    const name = t.name || t;
                                    return <option key={name} value={name}>{name}</option>;
                                })}
                            </select>
                        </div>
                        <div>
                            <FieldLabel htmlFor="splice-start-install">Start install</FieldLabel>
                            <input id="splice-start-install" type="date" value={startInstall} onChange={(e) => setStartInstall(e.target.value)} className={inputCls} style={border(false)} />
                        </div>
                        <div>
                            <FieldLabel htmlFor="splice-released">Released</FieldLabel>
                            <input id="splice-released" type="date" value={released} onChange={(e) => setReleased(e.target.value)} className={inputCls} style={border(false)} />
                        </div>
                    </div>

                    <div>
                        <FieldLabel htmlFor="splice-budget-hrs">Budget install hours</FieldLabel>
                        <input
                            id="splice-budget-hrs"
                            type="number"
                            inputMode="decimal"
                            min="0"
                            step="0.5"
                            max={remaining ?? undefined}
                            value={budgetHrs}
                            onChange={(e) => setBudgetHrs(e.target.value)}
                            className={inputCls}
                            style={border(overPool || budgetNeedsPool)}
                            placeholder={remaining != null ? `up to ${fmtHrs(remaining)}` : ''}
                        />
                        <p className="text-jl-2 mt-1" style={{ color: overPool || budgetNeedsPool ? 'var(--fl-red-fg)' : 'var(--text-3)' }}>
                            {noPool
                                ? `${jobNumber}-${releaseNumber} has no install hours, so there is no budget to draw from.`
                                : overPool
                                    ? `Only ${fmtHrs(remaining)} hours remain on ${jobNumber}-${releaseNumber}. Anything beyond that is additional hours.`
                                    : `${fmtHrs(remaining)} of ${fmtHrs(total)} budget hours remain on ${jobNumber}-${releaseNumber}.`}
                        </p>
                    </div>

                    <div
                        className="border rounded-md"
                        style={{
                            padding: '10px 12px',
                            borderColor: additionalOn ? 'var(--fl-amber-fg)' : 'var(--border)',
                            background: additionalOn ? 'var(--fl-amber-bg)' : 'transparent',
                        }}
                    >
                        <label className="flex items-center gap-2 text-ink font-semibold cursor-pointer" style={{ fontSize: 13.5 }}>
                            <input
                                type="checkbox"
                                checked={additionalOn}
                                onChange={(e) => setAdditionalOn(e.target.checked)}
                            />
                            Additional install hours needed
                        </label>
                        <p className="text-jl-2 text-ink-3" style={{ marginTop: 2 }}>
                            Hours beyond the original's budget. They don't come out of the pool.
                        </p>
                        {additionalOn && (
                            <div className="space-y-3" style={{ marginTop: 10 }}>
                                <div>
                                    <FieldLabel htmlFor="splice-additional-hrs" required>Additional install hours</FieldLabel>
                                    <input
                                        id="splice-additional-hrs"
                                        type="number"
                                        inputMode="decimal"
                                        min="0"
                                        step="0.5"
                                        value={additionalHrs}
                                        onChange={(e) => setAdditionalHrs(e.target.value)}
                                        className={inputCls}
                                        style={border(additionalHrs !== '' && !extraValid)}
                                    />
                                </div>
                                <div>
                                    <FieldLabel htmlFor="splice-additional-note" required>Why are additional hours needed?</FieldLabel>
                                    <textarea
                                        id="splice-additional-note"
                                        rows={3}
                                        value={additionalNote}
                                        onChange={(e) => setAdditionalNote(e.target.value)}
                                        className={`${inputCls} resize-y`}
                                        style={border(false)}
                                        placeholder="e.g. GC added two stair landings after the release"
                                    />
                                </div>
                            </div>
                        )}
                    </div>

                    {totalHrs > 0 ? (
                        <p className="text-jl-2 text-ink-2">
                            {`Splice total: ${fmtHrs(totalHrs)} install hrs`}
                            {additionalOn && extra > 0 ? ` (${fmtHrs(budget)} budget + ${fmtHrs(extra)} additional)` : ''}
                        </p>
                    ) : zeroHour ? (
                        <p className="text-jl-2 text-ink-2" data-testid="zero-hour-note">
                            Zero-hour splice: no install hours, so no installer is needed. Use this for drop-ship
                            or material-only work (put “drop ship” in the description).
                        </p>
                    ) : null}

                    {error && (
                        <p className="text-jl-2" style={{ color: 'var(--fl-red-fg)' }} role="alert">{error}</p>
                    )}
                </div>

                <div className="shrink-0 border-t border-hairline flex justify-end gap-2" style={{ padding: '10px 18px' }}>
                    <button
                        type="button"
                        onClick={onClose}
                        className="text-ink-2 bg-transparent border border-hairline-strong rounded-[7px] font-semibold hover:bg-surface-2"
                        style={{ fontSize: 13, padding: '6px 13px' }}
                    >
                        Cancel
                    </button>
                    <button
                        type="submit"
                        disabled={!canSubmit}
                        className="font-semibold border-0 text-white rounded-[7px] disabled:opacity-50 disabled:cursor-not-allowed"
                        style={{ fontSize: 13, padding: '6px 13px', background: 'var(--accent)' }}
                    >
                        {submitting ? 'Creating…' : `Create ${jobNumber}-${nextNumber}`}
                    </button>
                </div>
            </form>
        </div>
    );
}

export default SpliceReleaseModal;
