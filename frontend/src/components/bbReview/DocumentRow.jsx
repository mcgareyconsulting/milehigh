/**
 * One document row inside the BB review workspace (SubmittalDetailsModal).
 *
 * Renders a single drawing attached to a Procore submittal and drives its whole
 * lifecycle from one contextual primary action:
 *   not downloaded → [Pull]      downloaded → [Review]
 *   reviewing      → progress    reviewed   → verdict tally + [Findings ▾] + [Re-run]
 *
 * Findings expand IN PLACE (accordion). Download state and the completed-review summary
 * are lifted to the parent via onUpdate so they survive a collapse; the findings list and
 * accept/reject feedback are row-local UI. Severity colors come from ./urgency.js — the
 * app's one finding-severity vocabulary — never invented here.
 */
import React, { useEffect, useRef, useState } from 'react';

import { draftingWorkLoadApi } from '../../services/draftingWorkLoadApi';
import { URGENCY_STYLES, urgencyOf } from './urgency';

// The review runs on a background thread server-side (the Claude call takes minutes),
// so we enqueue it and poll the GET endpoint until it lands.
const POLL_MS = 5000;

const SOURCE_BADGE = {
    originating: { label: 'originating', cls: 'bg-accent-50 text-accent-600 dark:bg-accent-500/20 dark:text-accent-200' },
    approver: { label: 'approver markup', cls: 'bg-slate-100 text-slate-600 dark:bg-slate-600 dark:text-slate-200' },
};

function kb(bytes) {
    if (!bytes && bytes !== 0) return '';
    return `${Math.round(bytes / 1024)} KB`;
}

function relTime(iso) {
    if (!iso) return '';
    const then = new Date(iso).getTime();
    if (Number.isNaN(then)) return '';
    const secs = Math.floor((Date.now() - then) / 1000);
    if (secs < 60) return 'just now';
    const mins = Math.floor(secs / 60);
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.floor(hrs / 24)}d ago`;
}

// Normalize stored feedback (array or index-keyed object) into { [index]: { decision, notes } }.
function normalizeFeedback(feedback) {
    const map = {};
    if (!feedback) return map;
    if (Array.isArray(feedback)) {
        feedback.forEach((fb) => {
            if (fb && fb.finding_index != null) map[fb.finding_index] = { decision: fb.decision, notes: fb.notes };
        });
    } else if (typeof feedback === 'object') {
        Object.entries(feedback).forEach(([k, fb]) => {
            if (fb) map[k] = { decision: fb.decision, notes: fb.notes };
        });
    }
    return map;
}

function debugFrom(err) {
    const data = err?.originalError?.response?.data;
    if (!data) return null;
    const bits = {};
    if (data.tried) bits.tried = data.tried;
    if (data.candidates) bits.candidates = data.candidates;
    return Object.keys(bits).length ? bits : null;
}

function TallyChips({ tally, hold }) {
    const t = tally || {};
    const critical = t.critical || 0;
    const confirm = (t.high || 0) + (t.moderate || 0) + (t.low || 0);
    const clear = t.cleared || 0;
    return (
        <div className="flex items-center gap-1.5 flex-wrap">
            {critical > 0 && (
                <span className={`text-[11px] font-semibold px-1.5 py-0.5 rounded ${URGENCY_STYLES.critical.chip}`}>
                    ⛔ {critical} critical
                </span>
            )}
            {confirm > 0 && (
                <span className={`text-[11px] font-semibold px-1.5 py-0.5 rounded ${URGENCY_STYLES.moderate.chip}`}>
                    ⚠ {confirm} to confirm
                </span>
            )}
            <span className={`text-[11px] font-semibold px-1.5 py-0.5 rounded ${URGENCY_STYLES.cleared.chip}`}>
                ✓ {clear} clear
            </span>
            {hold && (
                <span className="text-[11px] font-bold px-1.5 py-0.5 rounded bg-red-600 text-white">HOLD</span>
            )}
        </div>
    );
}

function FindingRow({ finding, index, submittalId, attachmentId, reviewId, initial, onCite }) {
    const bucket = urgencyOf(finding);
    const style = URGENCY_STYLES[bucket] || URGENCY_STYLES.low;
    const [decision, setDecision] = useState(initial?.decision || null);
    const [busy, setBusy] = useState(false);
    const [err, setErr] = useState(null);

    const canCite = finding?.page != null && typeof onCite === 'function';
    const citeProps = canCite
        ? {
            onClick: onCite,
            role: 'button',
            className: 'cursor-pointer rounded hover:bg-amber-50 dark:hover:bg-amber-900/20 transition-colors',
        }
        : {};

    const choose = async (value) => {
        if (busy) return;
        setBusy(true);
        setErr(null);
        const prev = decision;
        setDecision(value);
        try {
            await draftingWorkLoadApi.saveProcoreDocumentReviewFeedback(submittalId, attachmentId, reviewId, {
                finding_index: index,
                decision: value,
                rule_id: finding?.rule_id || null,
                finding,
            });
        } catch (e) {
            setDecision(prev);
            setErr(e?.message || 'Failed to save');
        } finally {
            setBusy(false);
        }
    };

    return (
        <div className={`rounded-md border border-gray-200 dark:border-slate-600 border-l-4 ${style.stripe} bg-white dark:bg-slate-800 p-2 text-sm`}>
            <div {...citeProps}>
                <div className="flex items-center gap-2 flex-wrap">
                    <span className={`text-[11px] font-semibold px-1.5 py-0.5 rounded ${style.chip}`}>{style.label}</span>
                    {finding?.location && (
                        <span className="text-xs text-gray-500 dark:text-slate-400">{finding.location}</span>
                    )}
                    {finding?.page != null && (
                        <span className="text-xs text-amber-700 dark:text-amber-400 font-medium">p{finding.page} · jump ↵</span>
                    )}
                    {finding?.rule_id && (
                        <span className="text-xs text-gray-400 dark:text-slate-500 ml-auto">{finding.rule_id}</span>
                    )}
                </div>
                {finding?.issue && <p className="text-gray-800 dark:text-slate-100 mt-1">{finding.issue}</p>}
            </div>
            {finding?.computation && (
                <p className="text-xs text-gray-600 dark:text-slate-400 mt-1 font-mono whitespace-pre-wrap break-words">
                    {finding.computation}
                </p>
            )}
            {reviewId != null && (
                <div className="mt-1.5 flex items-center gap-1.5">
                    <button
                        type="button"
                        onClick={() => choose('accepted')}
                        disabled={busy}
                        className={`text-[11px] font-semibold px-2 py-0.5 rounded border transition-colors disabled:opacity-50 ${
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
                        className={`text-[11px] font-semibold px-2 py-0.5 rounded border transition-colors disabled:opacity-50 ${
                            decision === 'rejected'
                                ? 'bg-red-600 text-white border-red-600'
                                : 'bg-white dark:bg-slate-700 text-red-700 dark:text-red-300 border-red-300 dark:border-red-700 hover:bg-red-50 dark:hover:bg-red-900/30'
                        }`}
                    >
                        ✕ Reject
                    </button>
                    {busy && <span className="text-[10px] text-gray-400 dark:text-slate-500">saving…</span>}
                    {err && <span className="text-[10px] text-red-600 dark:text-red-400">{err}</span>}
                </div>
            )}
        </div>
    );
}

export default function DocumentRow({ submittalId, doc, model, onUpdate, onView, onCiteSource, activeAttachmentId }) {
    const [pulling, setPulling] = useState(false);
    const [reviewing, setReviewing] = useState(false);
    const [expanded, setExpanded] = useState(false);
    const [findings, setFindings] = useState(null);
    const [feedbackMap, setFeedbackMap] = useState({});
    const [findingsLoading, setFindingsLoading] = useState(false);
    const [error, setError] = useState(null);
    const [errorDebug, setErrorDebug] = useState(null);
    const [showDebug, setShowDebug] = useState(false);
    const pollRef = useRef(null);

    const clearPoll = () => {
        if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    };

    const attachmentId = doc.attachment_id;
    const review = doc.review || null;
    const reviewId = review?.review_id ?? null;
    const source = SOURCE_BADGE[doc.source] || SOURCE_BADGE.originating;
    const isActive = activeAttachmentId != null && activeAttachmentId === attachmentId;

    const clearError = () => { setError(null); setErrorDebug(null); setShowDebug(false); };

    const handlePull = async () => {
        clearError();
        setPulling(true);
        try {
            const res = await draftingWorkLoadApi.pullProcoreDocument(submittalId, attachmentId);
            onUpdate(attachmentId, {
                downloaded: true,
                size_bytes: res.size_bytes ?? doc.size_bytes,
                name: res.name || doc.name,
                source: res.source || doc.source,
            });
        } catch (e) {
            setError(e?.message || 'Pull failed');
            setErrorDebug(debugFrom(e));
        } finally {
            setPulling(false);
        }
    };

    // Fold a landed review (complete or error) from the GET endpoint into row + parent state.
    const applyReview = (r) => {
        onUpdate(attachmentId, {
            review: {
                review_id: r.review_id,
                status: r.status,
                model: r.model || model,
                completed_at: r.completed_at || new Date().toISOString(),
                tally: r.tally || {},
                hold_recommended: !!r.hold_recommended,
            },
        });
        setFindings(Array.isArray(r.findings) ? r.findings : []);
        setFeedbackMap(normalizeFeedback(r.feedback));
        setExpanded(true);
    };

    // Poll the GET endpoint until the background review lands (server runs it off-request).
    const startPolling = () => {
        clearPoll();
        setReviewing(true);
        pollRef.current = setInterval(async () => {
            try {
                const { review: r } = await draftingWorkLoadApi.fetchProcoreDocumentReview(submittalId, attachmentId);
                if (!r || r.status === 'pending') return;
                clearPoll();
                setReviewing(false);
                if (r.status === 'error') {
                    setError(r.error || 'Review failed');
                    // Lift the error status too, so the parent row doesn't stay stale/pending.
                    onUpdate(attachmentId, {
                        review: { review_id: r.review_id, status: 'error', model: r.model || model },
                    });
                } else {
                    applyReview(r);
                }
            } catch { /* transient network blip — keep polling */ }
        }, POLL_MS);
    };

    // Resume polling if the row mounts with a review already running server-side, and always
    // stop polling on unmount (e.g. the modal closes mid-review).
    useEffect(() => {
        if (doc.review?.status === 'pending') startPolling();
        return clearPoll;
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const handleReview = async () => {
        clearError();
        clearPoll();
        setReviewing(true);
        try {
            // Returns 202 with a pending row; the review itself runs on a background thread.
            await draftingWorkLoadApi.runProcoreDocumentReview(submittalId, attachmentId, { model, reviewOnly: true });
            startPolling();
        } catch (e) {
            clearPoll();
            setReviewing(false);
            setError(e?.message || 'Review failed');
            setErrorDebug(debugFrom(e));
        }
    };

    const loadFindings = async () => {
        setFindingsLoading(true);
        clearError();
        try {
            const { review: r } = await draftingWorkLoadApi.fetchProcoreDocumentReview(submittalId, attachmentId);
            setFindings(Array.isArray(r?.findings) ? r.findings : []);
            setFeedbackMap(normalizeFeedback(r?.feedback));
        } catch (e) {
            setError(e?.message || 'Failed to load findings');
            setErrorDebug(debugFrom(e));
        } finally {
            setFindingsLoading(false);
        }
    };

    const toggleFindings = () => {
        const next = !expanded;
        setExpanded(next);
        if (next && findings === null && !findingsLoading) loadFindings();
    };

    // ── Contextual status line + primary action ───────────────────────────────
    let statusEl = null;
    let actionEl = null;

    if (reviewing) {
        statusEl = (
            <div className="min-w-0">
                <span className="text-sm text-gray-700 dark:text-slate-200">🍌 Reviewing… (~2–4 min)</span>
                <div className="mt-1 h-1.5 w-40 max-w-full overflow-hidden rounded bg-gray-200 dark:bg-slate-600">
                    <div className="h-full w-1/3 rounded bg-indigo-500 animate-pulse" />
                </div>
            </div>
        );
    } else if (review && review.status === 'error') {
        // A failed review renders as a failure, not "Reviewed · 0 clear".
        statusEl = (
            <span className="text-sm text-red-600 dark:text-red-400">🍌 Review failed</span>
        );
        actionEl = (
            <button
                onClick={handleReview}
                className="px-3 py-1.5 text-sm font-medium bg-indigo-600 text-white rounded hover:bg-indigo-700 transition-colors shrink-0"
            >
                Retry review
            </button>
        );
    } else if (review) {
        statusEl = (
            <div className="min-w-0 space-y-1">
                <span className="text-sm text-gray-700 dark:text-slate-200">
                    🍌 Reviewed · {review.model || '—'}{review.completed_at ? ` · ${relTime(review.completed_at)}` : ''}
                </span>
                <TallyChips tally={review.tally} hold={review.hold_recommended} />
            </div>
        );
        actionEl = (
            <div className="flex items-center gap-2 shrink-0">
                <button
                    onClick={toggleFindings}
                    className="px-2.5 py-1 text-xs font-medium rounded border border-gray-300 dark:border-slate-600 text-gray-700 dark:text-slate-200 hover:bg-gray-100 dark:hover:bg-slate-700 transition-colors"
                >
                    Findings {expanded ? '▴' : '▾'}
                </button>
                <button
                    onClick={handleReview}
                    className="px-2.5 py-1 text-xs font-medium rounded text-indigo-600 dark:text-indigo-300 hover:bg-indigo-50 dark:hover:bg-indigo-900/30 transition-colors"
                    title="Re-run the BB review with the selected model"
                >
                    Re-run
                </button>
            </div>
        );
    } else if (doc.downloaded) {
        statusEl = (
            <span className="text-sm text-gray-700 dark:text-slate-200">⬇ Downloaded ({kb(doc.size_bytes)})</span>
        );
        actionEl = (
            <button
                onClick={handleReview}
                className="px-3 py-1.5 text-sm font-medium bg-indigo-600 text-white rounded hover:bg-indigo-700 transition-colors shrink-0"
            >
                Review
            </button>
        );
    } else {
        statusEl = <span className="text-sm text-gray-500 dark:text-slate-400">Not downloaded</span>;
        actionEl = (
            <button
                onClick={handlePull}
                disabled={pulling}
                className="px-3 py-1.5 text-sm font-medium bg-yellow-500 text-white rounded hover:bg-yellow-600 disabled:opacity-60 disabled:cursor-not-allowed transition-colors shrink-0"
            >
                {pulling ? 'Pulling…' : 'Pull'}
            </button>
        );
    }

    return (
        <div className={`p-3 ${reviewing ? 'opacity-70' : ''} ${isActive ? 'bg-amber-50/60 dark:bg-amber-900/10' : ''}`}>
            {/* Row top: filename + source badge + size */}
            <div className="flex items-center gap-2 flex-wrap">
                <span
                    className="text-sm font-medium text-gray-900 dark:text-white break-words min-w-0"
                    title={doc.name || 'drawing.pdf'}
                >
                    📄 {doc.name || 'drawing.pdf'}
                </span>
                <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${source.cls}`}>{source.label}</span>
                {doc.size_bytes ? (
                    <span className="text-xs text-gray-400 dark:text-slate-500">{kb(doc.size_bytes)}</span>
                ) : null}
            </div>

            {/* Row status + actions */}
            <div className="mt-2 flex items-start justify-between gap-3">
                {statusEl}
                <div className="flex items-center gap-2 shrink-0">
                    {doc.downloaded && onView ? (
                        <button
                            onClick={() => onView(doc)}
                            className="px-3 py-1.5 text-sm font-medium bg-gray-100 dark:bg-slate-700 text-gray-700 dark:text-slate-200 rounded hover:bg-gray-200 dark:hover:bg-slate-600 transition-colors"
                            title="Open the downloaded drawing in the viewer"
                        >
                            View
                        </button>
                    ) : null}
                    {actionEl}
                </div>
            </div>

            {/* Inline error with a debug disclosure */}
            {error ? (
                <div className="mt-2 text-xs text-red-600 dark:text-red-400">
                    <span>{error}</span>
                    {errorDebug ? (
                        <button
                            onClick={() => setShowDebug((s) => !s)}
                            className="ml-2 underline hover:no-underline"
                        >
                            details
                        </button>
                    ) : null}
                    {showDebug && errorDebug ? (
                        <pre className="mt-1 p-2 rounded bg-red-50 dark:bg-red-900/20 text-[11px] text-red-700 dark:text-red-300 overflow-x-auto whitespace-pre-wrap break-words">
                            {JSON.stringify(errorDebug, null, 2)}
                        </pre>
                    ) : null}
                </div>
            ) : null}

            {/* Findings accordion */}
            {review && expanded ? (
                <div className="mt-2 space-y-2">
                    {findingsLoading ? (
                        <p className="text-xs text-gray-500 dark:text-slate-400">Loading findings…</p>
                    ) : findings && findings.length === 0 ? (
                        <p className="text-sm text-green-600 dark:text-green-400">No findings — clear against BB's rules.</p>
                    ) : findings ? (
                        findings.map((f, i) => (
                            <FindingRow
                                key={i}
                                finding={f}
                                index={i}
                                submittalId={submittalId}
                                attachmentId={attachmentId}
                                reviewId={reviewId}
                                initial={feedbackMap[i]}
                                doc={doc}
                                onCite={() => onCiteSource && onCiteSource(doc, f)}
                            />
                        ))
                    ) : null}
                </div>
            ) : null}
        </div>
    );
}
