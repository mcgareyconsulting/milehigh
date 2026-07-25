/**
 * The shared Carmen-review finding card: verdict + severity + issue + worked math + the
 * sheet-cited values. Used by both the admin per-version panel (BBReviewPanel) and the
 * PM report (BBReviewReport). Urgency helpers live alongside in ./urgency.js.
 *
 * FindingFeedbackForm (accept/deny + notes) is the one training-loop control. Decision and
 * notes stay local until Save — one request commits both, so accept-then-type isn't two
 * saves. FeedbackControls wraps it for the release surface (jobsApi).
 */
import React, { useRef, useState } from 'react';

import { jobsApi } from '../../services/jobsApi';

const VERDICT_STYLES = {
    violation: { label: 'Violation', box: 'border-red-300 bg-red-50', text: 'text-red-700' },
    needs_field_verification: { label: 'Verify in field', box: 'border-amber-300 bg-amber-50', text: 'text-amber-700' },
    ok: { label: 'OK', box: 'border-green-200 bg-green-50', text: 'text-green-700' },
};

const SEVERITY_CHIP = {
    high: 'bg-red-100 text-red-700',
    medium: 'bg-amber-100 text-amber-700',
    low: 'bg-gray-100 text-gray-600',
};

export function Finding({ f }) {
    const v = VERDICT_STYLES[f.verdict] || VERDICT_STYLES.ok;
    return (
        <div className={`rounded-md border ${v.box} p-2 text-sm`}>
            <div className="flex items-center gap-2 flex-wrap">
                <span className={`text-xs font-bold uppercase tracking-wide ${v.text}`}>{v.label}</span>
                {f.severity && (
                    <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${SEVERITY_CHIP[f.severity] || SEVERITY_CHIP.low}`}>
                        {f.severity}
                    </span>
                )}
                {f.location && <span className="text-xs text-gray-500">{f.location}</span>}
            </div>
            {f.issue && <p className="text-gray-800 mt-1">{f.issue}</p>}
            {f.computation && (
                <p className="text-xs text-gray-600 mt-1 font-mono whitespace-pre-wrap break-words">{f.computation}</p>
            )}
            {Array.isArray(f.values_used) && f.values_used.length > 0 && (
                <ul className="mt-1 flex flex-wrap gap-1">
                    {f.values_used.map((val, i) => (
                        <li key={i} className="text-[11px] bg-white border border-gray-200 rounded px-1.5 py-0.5 text-gray-600">
                            {val.sheet ? <span className="font-semibold text-gray-800">{val.sheet}</span> : null}
                            {val.sheet ? ' · ' : ''}{val.name}: {val.value}
                        </li>
                    ))}
                </ul>
            )}
        </div>
    );
}

/**
 * FindingFeedbackForm — presentational accept/deny + notes training loop.
 *
 * Accept/Reject only select a decision (and focus the notes field). Nothing hits the
 * network until Save, which posts decision + notes together. Cmd/Ctrl+Enter also saves.
 * Seeded from any stored feedback so a returning reviewer sees their prior entry.
 *
 * @param {{ decision?: string|null, notes?: string }} [initial]
 * @param {(decision: string, notes: string) => Promise<void>} onSave
 * @param {string} [denyLabel]
 * @param {string} [className]
 */
export function FindingFeedbackForm({
    initial,
    onSave,
    denyLabel = 'Reject',
    className = '',
}) {
    const [decision, setDecision] = useState(initial?.decision || null);
    const [notes, setNotes] = useState(initial?.notes || '');
    const [saved, setSaved] = useState({
        decision: initial?.decision || null,
        notes: initial?.notes || '',
    });
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState(null);
    const notesRef = useRef(null);

    const dirty = decision !== saved.decision || notes !== (saved.notes || '');
    const canSave = Boolean(decision) && dirty && !busy;

    const choose = (value) => {
        setDecision(value);
        setError(null);
        // After picking yes/no, put the cursor in notes so typing is the next natural step.
        requestAnimationFrame(() => notesRef.current?.focus());
    };

    const save = async () => {
        if (!decision || busy) return;
        setBusy(true);
        setError(null);
        try {
            await onSave(decision, notes);
            setSaved({ decision, notes });
        } catch (err) {
            setError(err?.message || 'Failed to save');
        } finally {
            setBusy(false);
        }
    };

    const btnBase =
        'text-xs font-semibold px-2.5 py-1 rounded border transition-colors disabled:opacity-50';

    return (
        <div className={`mt-2 space-y-2 ${className}`.trim()}>
            <div className="flex items-center gap-1.5 flex-wrap">
                <button
                    type="button"
                    onClick={() => choose('accepted')}
                    disabled={busy}
                    className={`${btnBase} ${
                        decision === 'accepted'
                            ? 'bg-green-600 text-white border-green-600'
                            : 'bg-white dark:bg-slate-700 text-green-700 dark:text-green-300 border-green-300 dark:border-green-700 hover:bg-green-50 dark:hover:bg-green-900/30'
                    }`}
                >
                    ✓ Accept
                </button>
                <button
                    type="button"
                    onClick={() => choose('rejected')}
                    disabled={busy}
                    className={`${btnBase} ${
                        decision === 'rejected'
                            ? 'bg-red-600 text-white border-red-600'
                            : 'bg-white dark:bg-slate-700 text-red-700 dark:text-red-300 border-red-300 dark:border-red-700 hover:bg-red-50 dark:hover:bg-red-900/30'
                    }`}
                >
                    ✕ {denyLabel}
                </button>
                {busy && (
                    <span className="text-[11px] text-gray-400 dark:text-slate-500">Saving…</span>
                )}
                {!busy && dirty && decision && (
                    <span className="text-[11px] text-amber-600 dark:text-amber-400">Unsaved</span>
                )}
                {!busy && !dirty && saved.decision && (
                    <span className="text-[11px] text-green-600 dark:text-green-400">Saved</span>
                )}
                {error && (
                    <span className="text-[11px] text-red-600 dark:text-red-400">{error}</span>
                )}
            </div>

            <textarea
                ref={notesRef}
                rows={3}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                onKeyDown={(e) => {
                    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter' && canSave) {
                        e.preventDefault();
                        save();
                    }
                }}
                placeholder={
                    decision
                        ? 'Add a note about this finding (optional)…'
                        : 'Accept or reject first, then add an optional note…'
                }
                className="w-full min-h-[4.5rem] text-sm px-3 py-2 rounded-md border border-gray-200 dark:border-slate-600 bg-white dark:bg-slate-700 text-gray-800 dark:text-slate-100 placeholder:text-gray-400 dark:placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-accent-400/40 focus:border-accent-400 resize-y"
            />

            <div className="flex items-center gap-2 flex-wrap">
                <button
                    type="button"
                    onClick={save}
                    disabled={!canSave}
                    className="text-xs font-semibold px-3 py-1.5 rounded-md bg-slate-800 dark:bg-slate-200 text-white dark:text-slate-900 hover:bg-slate-700 dark:hover:bg-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                    {busy ? 'Saving…' : 'Save feedback'}
                </button>
                <span className="text-[11px] text-gray-400 dark:text-slate-500">
                    {decision
                        ? '⌘/Ctrl+Enter to save'
                        : 'Pick Accept or Reject, then Save'}
                </span>
            </div>
        </div>
    );
}

/**
 * FeedbackControls — release-surface wrapper: persists via jobsApi.
 * No-ops without releaseId/reviewId.
 */
export function FeedbackControls({ releaseId, reviewId, findingIndex, finding, initial }) {
    if (!releaseId || !reviewId) return null;

    return (
        <FindingFeedbackForm
            initial={initial}
            denyLabel="Deny"
            onSave={async (decision, notes) => {
                await jobsApi.saveCarmenReviewFeedback(releaseId, reviewId, {
                    finding_index: findingIndex,
                    rule_id: finding?.rule_id || null,
                    decision,
                    notes,
                    finding,
                });
            }}
        />
    );
}

export default Finding;
