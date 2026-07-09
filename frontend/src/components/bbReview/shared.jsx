/**
 * The shared BB-review finding card: verdict + severity + issue + worked math + the
 * sheet-cited values. Used by both the admin per-version panel (BBReviewPanel) and the
 * PM report (BBReviewReport). Urgency helpers live alongside in ./urgency.js.
 *
 * FeedbackControls (the accept/deny/notes training loop) also lives here so both surfaces
 * render it identically. Feedback is keyed by the finding's index in the review's stored
 * `findings` array, so a decision made on either surface refers to the same finding.
 */
import React, { useState } from 'react';

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
 * FeedbackControls — the yes/no/notes training loop for one finding. Accept/deny writes
 * immediately; notes save on blur (or the Save button). Seeded from any stored feedback so
 * a returning reviewer sees their prior decision. No-ops without releaseId/reviewId.
 */
export function FeedbackControls({ releaseId, reviewId, findingIndex, finding, initial }) {
    const [decision, setDecision] = useState(initial?.decision || null);
    const [notes, setNotes] = useState(initial?.notes || '');
    const [savedNotes, setSavedNotes] = useState(initial?.notes || '');
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState(null);

    if (!releaseId || !reviewId) return null;

    const save = async (nextDecision, nextNotes) => {
        setBusy(true);
        setError(null);
        try {
            await jobsApi.saveBBReviewFeedback(releaseId, reviewId, {
                finding_index: findingIndex,
                rule_id: finding?.rule_id || null,
                decision: nextDecision,
                notes: nextNotes,
                finding,
            });
            setSavedNotes(nextNotes);
        } catch (err) {
            setError(err?.message || 'Failed to save');
        } finally {
            setBusy(false);
        }
    };

    const choose = (value) => { setDecision(value); save(value, notes); };
    const notesDirty = notes !== savedNotes;

    return (
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            <button
                type="button"
                onClick={() => choose('accepted')}
                disabled={busy}
                className={`text-[11px] font-semibold px-2 py-0.5 rounded border transition-colors disabled:opacity-50 ${
                    decision === 'accepted'
                        ? 'bg-green-600 text-white border-green-600'
                        : 'bg-white text-green-700 border-green-300 hover:bg-green-50'
                }`}
            >
                ✓ Accept
            </button>
            <button
                type="button"
                onClick={() => choose('rejected')}
                disabled={busy}
                className={`text-[11px] font-semibold px-2 py-0.5 rounded border transition-colors disabled:opacity-50 ${
                    decision === 'rejected'
                        ? 'bg-red-600 text-white border-red-600'
                        : 'bg-white text-red-700 border-red-300 hover:bg-red-50'
                }`}
            >
                ✕ Deny
            </button>
            <input
                type="text"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                onBlur={() => { if (decision && notesDirty) save(decision, notes); }}
                placeholder="Add a note (optional)…"
                className="flex-1 min-w-[8rem] text-[11px] px-2 py-0.5 rounded border border-gray-200 bg-white text-gray-700 placeholder:text-gray-400 focus:outline-none focus:border-accent-400"
            />
            {busy && <span className="text-[10px] text-gray-400">saving…</span>}
            {!busy && decision && !notesDirty && <span className="text-[10px] text-green-600">saved</span>}
            {error && <span className="text-[10px] text-red-600">{error}</span>}
        </div>
    );
}

export default Finding;
