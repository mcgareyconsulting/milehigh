/**
 * BBReviewPanel — Banana Boy code-compliance review for one PDF drawing version.
 *
 * Admin-only (gate via the `enabled` prop; the backend also enforces @admin_required).
 * Self-contained: loads the latest review on mount, lets an admin kick off a new one,
 * polls while it's `pending`, and renders the findings (severity chip, verdict,
 * computation, and the sheet citations BB used).
 */
import React, { useEffect, useRef, useState } from 'react';

import { jobsApi } from '../services/jobsApi';
import { Finding } from './bbReview/shared';
import { actionableCount } from './bbReview/urgency';

const POLL_MS = 5000;

export function BBReviewPanel({ releaseId, versionId, enabled }) {
    const [open, setOpen] = useState(false);
    const [review, setReview] = useState(undefined);   // undefined=unloaded, null=none
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState(null);
    const pollRef = useRef(null);

    const clearPoll = () => {
        if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    };

    const load = async () => {
        try {
            const r = await jobsApi.getBBReview(releaseId, versionId);
            setReview(r);
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
                if (!r || r.status !== 'pending') clearPoll();
            } catch { /* keep polling; transient */ }
        }, POLL_MS);
    };

    // Load once when the panel is first expanded.
    useEffect(() => {
        if (open && review === undefined) load();
        return clearPoll;
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open]);

    useEffect(() => clearPoll, []);

    const runReview = async () => {
        setBusy(true);
        setError(null);
        try {
            const r = await jobsApi.requestBBReview(releaseId, versionId);
            setReview(r);
            startPoll();
        } catch (err) {
            setError(err?.message || 'Failed to start review');
        } finally {
            setBusy(false);
        }
    };

    if (!enabled) return null;

    const findings = review?.findings || [];
    // Count everything the PM must act on (violations + needs-verification), not just violations.
    const flags = actionableCount(findings);
    const isPending = review?.status === 'pending';
    const canRun = !isPending && !busy;

    return (
        <div className="mt-2 pt-2 border-t border-gray-100">
            <button
                type="button"
                onClick={() => setOpen((o) => !o)}
                className="text-xs font-medium text-yellow-700 hover:text-yellow-800 flex items-center gap-1"
            >
                <span>{open ? '▾' : '▸'}</span>
                <span>🍌 BB review</span>
                {review?.status === 'complete' && (
                    <span className={flags ? 'text-red-600 font-semibold' : 'text-green-600'}>
                        {flags ? `${flags} flag${flags > 1 ? 's' : ''}` : 'clear'}
                    </span>
                )}
                {isPending && <span className="text-gray-400 italic">running…</span>}
            </button>

            {open && (
                <div className="mt-2 space-y-2">
                    {review === undefined && <p className="text-xs text-gray-400 italic">Loading…</p>}

                    {review === null && (
                        <p className="text-xs text-gray-500">
                            Submit this set to Banana Boy for a code-compliance check.
                        </p>
                    )}

                    {isPending && (
                        <p className="text-xs text-gray-500 italic">
                            BB is reviewing the full set — this takes a couple of minutes.
                        </p>
                    )}

                    {review?.status === 'error' && (
                        <p className="text-xs text-red-600">Review failed: {review.error || 'unknown error'}</p>
                    )}

                    {review?.status === 'complete' && findings.length === 0 && (
                        <p className="text-xs text-green-700">No issues found against BB's known failure modes.</p>
                    )}

                    {review?.status === 'complete' && findings.map((f, i) => <Finding key={i} f={f} />)}

                    {error && <p className="text-xs text-red-600">{error}</p>}

                    <div className="flex items-center gap-2 pt-1">
                        <button
                            type="button"
                            onClick={runReview}
                            disabled={!canRun}
                            className="px-3 py-1.5 text-xs bg-yellow-500 text-white rounded-md font-semibold disabled:opacity-50"
                        >
                            {review ? 'Re-run BB review' : 'Submit to BB for review'}
                        </button>
                        {review?.status === 'complete' && review.model && (
                            <span className="text-[11px] text-gray-400">
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
