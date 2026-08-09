/**
 * BBReviewPanel — Carmen code-compliance review for one PDF drawing version.
 *
 * Gated via `enabled` (admin or drafter). Loads the latest review, can enqueue
 * a new one, polls while pending, and renders findings + accept/reject feedback.
 * Optional onCite jumps the hub PDF viewer to a finding's page.
 */
import React, { useEffect, useRef, useState } from 'react';

import { jobsApi } from '../services/jobsApi';
import { FeedbackControls } from './bbReview/shared';
import { actionableCount, URGENCY_STYLES, urgencyOf } from './bbReview/urgency';

const POLL_MS = 5000;

export function BBReviewPanel({
    releaseId,
    versionId,
    enabled,
    /** When true, load review as soon as enabled (for badge + default expand). */
    autoLoad = false,
    /** (page:number, ruleId?:string) => void — only called when finding has a page. */
    onCite = null,
    /** (count:number) => void — actionable findings for the hub badge. */
    onFlagsChange = null,
    defaultOpen = false,
}) {
    const [open, setOpen] = useState(defaultOpen);
    const [review, setReview] = useState(undefined);   // undefined=unloaded, null=none
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState(null);
    const pollRef = useRef(null);
    const flagsReported = useRef(null);

    const clearPoll = () => {
        if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    };

    const reportFlags = (r) => {
        if (!onFlagsChange) return;
        const findings = r?.status === 'complete' ? (r.findings || []) : [];
        const n = actionableCount(findings);
        if (flagsReported.current === n) return;
        flagsReported.current = n;
        onFlagsChange(n);
    };

    const load = async () => {
        try {
            const r = await jobsApi.getBBReview(releaseId, versionId);
            setReview(r);
            reportFlags(r);
            if (r && r.status === 'pending') startPoll();
            else clearPoll();
        } catch (err) {
            setError(err?.message || 'Failed to load review');
        }
    };

    const startPoll = () => {
        clearPoll();
        pollRef.current = setInterval(async () => {
            try {
                const r = await jobsApi.getBBReview(releaseId, versionId);
                setReview(r);
                reportFlags(r);
                if (!r || r.status !== 'pending') clearPoll();
            } catch { /* keep polling; transient */ }
        }, POLL_MS);
    };

    // Load when expanded, or autoLoad when enabled.
    useEffect(() => {
        if (!enabled) return undefined;
        if ((open || autoLoad) && review === undefined) load();
        return clearPoll;
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open, autoLoad, enabled, releaseId, versionId]);

    useEffect(() => clearPoll, []);

    const runReview = async () => {
        setBusy(true);
        setError(null);
        try {
            const r = await jobsApi.requestBBReview(releaseId, versionId);
            setReview(r);
            reportFlags(r);
            startPoll();
            setOpen(true);
        } catch (err) {
            setError(err?.message || 'Failed to start review');
        } finally {
            setBusy(false);
        }
    };

    if (!enabled) return null;

    const findings = review?.findings || [];
    const flags = actionableCount(findings);
    const isPending = review?.status === 'pending';
    const canRun = !isPending && !busy;

    return (
        <div className="mt-2 pt-2 border-t border-hairline">
            <button
                type="button"
                onClick={() => setOpen((o) => !o)}
                className="text-xs font-medium flex items-center gap-1 bg-transparent border-0 cursor-pointer"
                style={{ color: 'var(--st-amber-fg)' }}
            >
                <span>{open ? '▾' : '▸'}</span>
                <span>Findings</span>
                {review?.status === 'complete' && (
                    <span
                        className="font-semibold"
                        style={{ color: flags ? 'var(--fl-red-bg)' : 'var(--st-green-fg)' }}
                    >
                        {flags ? `${flags} to confirm` : 'clear'}
                    </span>
                )}
                {isPending && <span className="text-ink-3 italic">running…</span>}
            </button>

            {open && (
                <div className="mt-2 space-y-2">
                    {review === undefined && <p className="text-xs text-ink-3 italic">Loading…</p>}

                    {review === null && (
                        <p className="text-xs text-ink-3">
                            No review yet — run Carmen for a code-compliance check.
                        </p>
                    )}

                    {isPending && (
                        <p className="text-xs text-ink-3 italic">
                            Carmen is reviewing — this can take a couple of minutes.
                        </p>
                    )}

                    {review?.status === 'error' && (
                        <p className="text-xs" style={{ color: 'var(--fl-red-bg)' }}>
                            Review failed: {review.error || 'unknown error'}
                        </p>
                    )}

                    {review?.status === 'complete' && findings.length === 0 && (
                        <p className="text-xs" style={{ color: 'var(--st-green-fg)' }}>
                            No issues found.
                        </p>
                    )}

                    {review?.status === 'complete' && findings.map((f, i) => {
                        const bucket = urgencyOf(f);
                        const style = URGENCY_STYLES[bucket] || URGENCY_STYLES.low;
                        const canJump = f?.page != null && typeof onCite === 'function';
                        return (
                            <div
                                key={i}
                                className={`rounded-md border border-hairline border-l-4 ${style.stripe} bg-surface p-2.5 text-sm`}
                            >
                                <div className="flex items-center gap-2 flex-wrap">
                                    <span className={`text-[11px] font-semibold px-1.5 py-0.5 rounded ${style.chip}`}>
                                        {style.label}
                                    </span>
                                    {f?.location && (
                                        <span className="text-xs text-ink-3">{f.location}</span>
                                    )}
                                    {f?.rule_id && (
                                        <span className="text-xs font-mono text-ink-3 ml-auto">{f.rule_id}</span>
                                    )}
                                </div>
                                {f?.issue && <p className="text-ink mt-1">{f.issue}</p>}
                                {f?.computation && (
                                    <p
                                        className="text-xs font-mono text-ink-2 mt-1 whitespace-pre-wrap break-words bg-surface-2 rounded"
                                        style={{ padding: '6px 8px' }}
                                    >
                                        {f.computation}
                                    </p>
                                )}
                                {canJump && (
                                    <button
                                        type="button"
                                        onClick={() => onCite(f.page, f.rule_id || null)}
                                        className="mt-1.5 text-xs font-medium bg-transparent border-0 cursor-pointer"
                                        style={{ color: '#b45309' }}
                                    >
                                        p{f.page} · jump ↵
                                    </button>
                                )}
                                {/* Hide jump when no page — per product decision. */}
                                <FeedbackControls
                                    releaseId={releaseId}
                                    reviewId={review.id}
                                    findingIndex={i}
                                    finding={f}
                                    initial={review.feedback?.[i]}
                                />
                            </div>
                        );
                    })}

                    {error && <p className="text-xs" style={{ color: 'var(--fl-red-bg)' }}>{error}</p>}

                    <div className="flex items-center gap-2 pt-1">
                        <button
                            type="button"
                            onClick={runReview}
                            disabled={!canRun}
                            className="px-3 py-1.5 text-xs font-semibold text-white rounded-md disabled:opacity-50 border-0 cursor-pointer"
                            style={{ background: 'var(--st-amber-fg)' }}
                        >
                            {review ? 'Re-run review' : 'Run Carmen review'}
                        </button>
                        {review?.status === 'complete' && review.model && (
                            <span className="text-[11px] text-ink-3">
                                {review.model}
                                {review.output_tokens ? ` · ${review.output_tokens} tok` : ''}
                            </span>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}

export default BBReviewPanel;
