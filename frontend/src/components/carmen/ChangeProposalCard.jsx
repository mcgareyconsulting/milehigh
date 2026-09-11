/**
 * @milehigh-header
 * schema_version: 1
 * purpose: The confirmation gate for a spoken release edit. Shows exactly what Carmen is
 *          about to change, from and to, and writes nothing until a human confirms.
 *          After applying it turns into a receipt with per-change Undo.
 * exports:
 *   ChangeProposalCard: default. Props { proposal, outcome, onApplied, disabled, registerConfirm }.
 * imports_from: [react, ../../services/carmenVoiceApi]
 * imported_by: [components/BBChatWidget.jsx]
 * invariants:
 *   - The plan and token are passed back to the server untouched; editing either
 *     invalidates the signature and the write is refused.
 *   - Confirm is disabled while applying, so a double-click can't double-write.
 *   - registerConfirm exposes the same handler the button uses, so saying "go ahead"
 *     takes the identical path — there is no second way to write.
 *   - A failed change is shown as failed, never folded into the success count.
 *   - Applying or undoing announces `carmen:data-changed` so the page behind the widget
 *     refreshes now rather than on its next 30s poll.
 *   - The OUTCOME is owned by the caller, not this component. It survived a remount as
 *     local state exactly never: inserting a message above the card re-mounts it, and the
 *     card would go back to "nothing is saved yet" after a write had already happened.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { applyLiveChanges, undoLiveEvent } from '../../services/carmenVoiceApi';

/** Tell whatever page is behind the widget that release data just changed. */
function announceChange(plan) {
    window.dispatchEvent(new CustomEvent('carmen:data-changed', {
        detail: { job: plan?.job, release: plan?.release },
    }));
}

function Row({ label, from, to }) {
    return (
        <div className="flex items-baseline gap-2 text-[12px] leading-snug">
            <span className="shrink-0 w-[88px] text-gray-400 dark:text-slate-500">{label}</span>
            <span className="min-w-0 flex-1 text-gray-800 dark:text-slate-100 break-words">
                <span className="font-medium">{to}</span>
                {from && from !== '—' && (
                    <span className="text-gray-400 dark:text-slate-500"> &nbsp;←&nbsp; {from}</span>
                )}
            </span>
        </div>
    );
}

export default function ChangeProposalCard({ proposal, outcome = null, onApplied,
                                             disabled = false, registerConfirm }) {
    const [applying, setApplying] = useState(false);
    const [error, setError] = useState('');
    const [undone, setUndone] = useState({});
    const state = outcome ? 'done' : applying ? 'applying' : 'pending';
    const stateRef = useRef(state);
    stateRef.current = state;

    const plan = useMemo(() => proposal.plan || {}, [proposal]);
    const changes = plan.changes || [];
    const who = `${plan.job}-${plan.release}`;

    const confirm = useCallback(async () => {
        if (stateRef.current !== 'pending') return;
        setApplying(true);
        setError('');
        try {
            const result = await applyLiveChanges(proposal);
            if (result?.applied) announceChange(plan);
            onApplied?.(result);   // the caller stores it; this component stays stateless about it
        } catch (err) {
            setError(err?.response?.data?.error || 'That change could not be applied.');
        } finally {
            setApplying(false);
        }
    }, [proposal, plan, onApplied]);

    // Let the widget fire this when the person says "go ahead" instead of clicking.
    useEffect(() => {
        registerConfirm?.(confirm);
    }, [registerConfirm, confirm]);

    const undo = async (eventId) => {
        setUndone((p) => ({ ...p, [eventId]: 'working' }));
        try {
            await undoLiveEvent(eventId);
            announceChange(plan);
            setUndone((p) => ({ ...p, [eventId]: 'done' }));
        } catch {
            setUndone((p) => ({ ...p, [eventId]: 'failed' }));
        }
    };

    return (
        <div className="mt-2 rounded-xl border border-amber-300 dark:border-amber-700/70 bg-amber-50/70 dark:bg-amber-900/20 overflow-hidden">
            <div className="px-3 py-2 border-b border-amber-200 dark:border-amber-800/60">
                <p className="text-[12px] font-semibold text-gray-800 dark:text-slate-100">
                    {state === 'done'
                        ? `Applied to ${who}`
                        : `Change ${who}${changes.length > 1 ? ` — ${changes.length} changes` : ''}`}
                </p>
                {plan.job_name && (
                    <p className="text-[11px] text-gray-500 dark:text-slate-400 truncate">{plan.job_name}</p>
                )}
            </div>

            <div className="px-3 py-2 space-y-1.5">
                {changes.map((c) => (
                    <Row key={c.field} label={c.label} from={c.from_display} to={c.to_display} />
                ))}
            </div>

            {error && <p className="px-3 pb-2 text-[11px] text-red-600 dark:text-red-400">{error}</p>}

            {state !== 'done' ? (
                <div className="px-3 pb-2.5 flex items-center gap-2">
                    <button
                        type="button"
                        onClick={confirm}
                        disabled={disabled || state === 'applying'}
                        className="h-7 px-3 rounded-lg bg-accent-500 hover:bg-accent-600 disabled:opacity-50 text-white text-[12px] font-medium"
                    >
                        {state === 'applying' ? 'Saving…' : 'Confirm'}
                    </button>
                    <button
                        type="button"
                        onClick={() => onApplied?.({ cancelled: true })}
                        disabled={state === 'applying'}
                        className="h-7 px-3 rounded-lg border border-gray-300 dark:border-slate-600 text-[12px] text-gray-600 dark:text-slate-300 hover:bg-white/60 dark:hover:bg-slate-700"
                    >
                        Cancel
                    </button>
                    <span className="text-[10px] text-gray-400 dark:text-slate-500">Nothing is saved yet</span>
                </div>
            ) : (
                <div className="px-3 pb-2.5 space-y-1">
                    {outcome?.cancelled && (
                        <p className="text-[11px] text-gray-500 dark:text-slate-400">Cancelled — nothing was changed.</p>
                    )}
                    {(outcome?.results || []).map((r) => (
                        <div key={r.field} className="flex items-center gap-2 text-[11px]">
                            <span className={r.status === 'applied'
                                ? 'text-emerald-600 dark:text-emerald-400'
                                : 'text-red-600 dark:text-red-400'}>
                                {r.status === 'applied' ? '✓' : '✗'} {r.label}
                            </span>
                            {r.status === 'failed' && <span className="text-gray-500 truncate">{r.error}</span>}
                            {r.status === 'applied' && r.event_id && (
                                undone[r.event_id] === 'done'
                                    ? <span className="text-gray-400">undone</span>
                                    : (
                                        <button
                                            type="button"
                                            onClick={() => undo(r.event_id)}
                                            disabled={undone[r.event_id] === 'working'}
                                            className="ml-auto text-gray-400 hover:text-accent-500 underline underline-offset-2 disabled:opacity-50"
                                        >
                                            {undone[r.event_id] === 'working' ? 'undoing…'
                                                : undone[r.event_id] === 'failed' ? 'undo failed' : 'undo'}
                                        </button>
                                    )
                            )}
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
