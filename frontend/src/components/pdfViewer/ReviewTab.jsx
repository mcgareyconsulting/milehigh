/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Carmen code-compliance findings for the open drawing version, rendered in the
 *   hybrid viewer's right dock. Loads the latest review, enqueues a re-run, polls while
 *   pending, and jumps the canvas to a finding's cited page.
 * exports:
 *   ReviewTab: props { releaseId, versionId, enabled, onCite, onFlagsChange }
 * imports_from: [react, ../../services/jobsApi, ../bbReview/shared, ../bbReview/urgency]
 * imported_by: [frontend/src/components/pdfViewer/ViewerDock.jsx]
 * invariants:
 *   - Disabled (non admin/drafter) renders the gated empty state, never a request
 *   - Poll stops on unmount and whenever the review leaves 'pending'
 *   - Carmen chat is not built yet — the tab is findings only
 * updated_by_agent: 2026-09-05T00:00:00Z
 */
import React, { useEffect, useRef, useState } from 'react';

import { jobsApi } from '../../services/jobsApi';
import { FeedbackControls } from '../bbReview/shared';
import { actionableCount, URGENCY_STYLES, urgencyOf } from '../bbReview/urgency';

const POLL_MS = 5000;

export function ReviewTab({
    releaseId,
    versionId,
    enabled = false,
    onCite = null,
    onFlagsChange = null,
}) {
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
        const n = actionableCount(r?.status === 'complete' ? (r.findings || []) : []);
        if (flagsReported.current === n) return;
        flagsReported.current = n;
        onFlagsChange(n);
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

    // Reload whenever the dock switches to another version.
    useEffect(() => {
        if (!enabled || !releaseId || !versionId) return undefined;
        let cancelled = false;
        flagsReported.current = null;
        setReview(undefined);
        setError(null);
        (async () => {
            try {
                const r = await jobsApi.getBBReview(releaseId, versionId);
                if (cancelled) return;
                setReview(r);
                reportFlags(r);
                if (r && r.status === 'pending') startPoll();
                else clearPoll();
            } catch (err) {
                if (!cancelled) setError(err?.message || 'Failed to load review');
            }
        })();
        return () => { cancelled = true; clearPoll(); };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [enabled, releaseId, versionId]);

    useEffect(() => clearPoll, []);

    const runReview = async () => {
        setBusy(true);
        setError(null);
        try {
            const r = await jobsApi.requestBBReview(releaseId, versionId);
            setReview(r);
            reportFlags(r);
            startPoll();
        } catch (err) {
            setError(err?.message || 'Failed to start review');
        } finally {
            setBusy(false);
        }
    };

    if (!enabled) {
        return (
            <p className="text-ink-3" style={{ padding: '14px 12px', fontSize: 12.5 }}>
                Carmen reviews are available to drafters and admins.
            </p>
        );
    }

    const findings = review?.findings || [];
    const flags = actionableCount(findings);
    const isPending = review?.status === 'pending';

    return (
        <div className="flex flex-col min-h-0">
            {/* Pinned findings header */}
            <div
                className="shrink-0 flex items-center border-b border-hairline"
                style={{ gap: 8, padding: '10px 12px', background: '#fffbeb' }}
            >
                <span
                    className="font-bold uppercase"
                    style={{ fontSize: 12, letterSpacing: '.06em', color: 'var(--st-amber-fg)' }}
                >
                    Findings
                </span>
                {review?.status === 'complete' && (
                    <span
                        className="font-semibold"
                        style={{
                            fontSize: 11,
                            padding: '1px 6px',
                            borderRadius: 999,
                            background: flags ? '#fef3c7' : 'var(--st-green-bg)',
                            color: flags ? '#b45309' : 'var(--st-green-fg)',
                        }}
                    >
                        {flags ? `${flags} to confirm` : 'clear'}
                    </span>
                )}
                {isPending && <span className="text-ink-3 italic" style={{ fontSize: 12 }}>running…</span>}
                <button
                    type="button"
                    onClick={runReview}
                    disabled={isPending || busy}
                    className="ml-auto bg-transparent border-0 cursor-pointer font-semibold disabled:opacity-50"
                    style={{ fontSize: 12, color: 'var(--st-amber-fg)' }}
                >
                    {review ? 'Re-run ↻' : 'Run Carmen ↻'}
                </button>
            </div>

            <div className="flex-1 min-h-0 overflow-y-auto" style={{ padding: '10px 12px' }}>
                {review === undefined && <p className="text-xs text-ink-3 italic">Loading…</p>}
                {review === null && (
                    <p className="text-xs text-ink-3">
                        No review yet — run Carmen for a code-compliance check on this version.
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
                    <p className="text-xs" style={{ color: 'var(--st-green-fg)' }}>No issues found.</p>
                )}

                <div className="space-y-2">
                    {review?.status === 'complete' && findings.map((f, i) => {
                        const style = URGENCY_STYLES[urgencyOf(f)] || URGENCY_STYLES.low;
                        const canJump = f?.page != null && typeof onCite === 'function';
                        return (
                            <div
                                key={i}
                                className={`rounded-md border border-hairline border-l-4 ${style.stripe} bg-surface text-sm`}
                                style={{ padding: '8px 10px' }}
                            >
                                <div className="flex items-center gap-2 flex-wrap">
                                    <span className={`font-semibold px-1.5 py-0.5 rounded ${style.chip}`} style={{ fontSize: 11.5 }}>
                                        {style.label}
                                    </span>
                                    {f?.location && (
                                        <span className="text-ink-3" style={{ fontSize: 12.5 }}>{f.location}</span>
                                    )}
                                    {f?.rule_id && (
                                        <span className="font-mono text-ink-3 ml-auto" style={{ fontSize: 12 }}>{f.rule_id}</span>
                                    )}
                                </div>
                                {f?.issue && <p className="text-ink mt-1" style={{ fontSize: 13.5 }}>{f.issue}</p>}
                                {f?.computation && (
                                    <p
                                        className="font-mono text-ink-2 mt-1 whitespace-pre-wrap break-words bg-surface-2 rounded"
                                        style={{ padding: '6px 8px', fontSize: 12 }}
                                    >
                                        {f.computation}
                                    </p>
                                )}
                                {canJump && (
                                    <button
                                        type="button"
                                        onClick={() => onCite(f.page, f.rule_id || null)}
                                        className="mt-1.5 border-0 cursor-pointer font-bold"
                                        style={{
                                            fontSize: 11.5,
                                            padding: '1px 7px',
                                            borderRadius: 999,
                                            background: '#fef3c7',
                                            color: '#b45309',
                                        }}
                                    >
                                        p{f.page} · jump ↵
                                    </button>
                                )}
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
                </div>

                {error && <p className="text-xs mt-2" style={{ color: 'var(--fl-red-bg)' }}>{error}</p>}

                {review?.status === 'complete' && review.model && (
                    <p className="text-ink-3" style={{ fontSize: 11, marginTop: 8 }}>
                        {review.model}
                        {review.output_tokens ? ` · ${review.output_tokens} tok` : ''}
                    </p>
                )}
            </div>
        </div>
    );
}

export default ReviewTab;
