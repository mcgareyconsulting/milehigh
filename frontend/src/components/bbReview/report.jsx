/**
 * BBReviewReport — the PM-facing report for one release, rendered from the server's
 * assembled report object (app/brain/pdf_review/report.build_report):
 *   { review_id, headline, hold_recommended, tally, findings: [<f + urgency>],
 *     cleared: [...], feedback: { <finding_index>: {decision, notes} } }
 *
 * Verdict banner + urgency tally + findings ranked most-urgent-first (severity stripe +
 * urgency pill + the shared Finding detail). Each ranked finding carries an accept/deny +
 * notes control (the training loop) whose state is persisted to the DB. An admin also gets
 * a re-run button (for tuning verbosity/rules) via the onRerun prop.
 */
import React from 'react';

import { Finding, FeedbackControls } from './shared';
import { URGENCY_STYLES, URGENCY_ORDER } from './urgency';

const TALLY_LABELS = {
    critical: 'Critical', high: 'High', moderate: 'Moderate', low: 'Low', cleared: 'Cleared',
};

function RankedFinding({ f, index, releaseId, reviewId, feedback }) {
    const u = URGENCY_STYLES[f.urgency] || URGENCY_STYLES.low;
    // orig_index is the finding's slot in the review's stored `findings` array (set by
    // build_report); key feedback by it so it matches the drawing-panel surface.
    const findingIndex = Number.isInteger(f.orig_index) ? f.orig_index : index;
    return (
        <div className={`border-l-4 ${u.stripe} pl-2`}>
            <div className="flex items-center gap-2 mb-1">
                <span className={`text-[10px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded ${u.chip}`}>
                    {u.label}
                </span>
                {f.rule_id && <span className="text-[10px] text-gray-400 font-mono">{f.rule_id}</span>}
            </div>
            <Finding f={f} />
            <FeedbackControls
                releaseId={releaseId}
                reviewId={reviewId}
                findingIndex={findingIndex}
                finding={f}
                initial={feedback[findingIndex]}
            />
        </div>
    );
}

export function BBReviewReport({ report, releaseId, canRerun = false, rerunning = false, onRerun }) {
    if (!report) return null;
    const {
        headline, hold_recommended, tally = {}, findings = [], cleared = [],
        review_id: reviewId, feedback = {},
    } = report;

    return (
        <div className="space-y-3">
            {/* verdict banner */}
            <div className={`rounded-md border p-2.5 text-sm ${hold_recommended
                ? 'border-red-300 bg-red-50 text-red-800'
                : (findings.length ? 'border-amber-300 bg-amber-50 text-amber-800'
                    : 'border-green-200 bg-green-50 text-green-800')}`}>
                <span className="font-semibold">{headline}</span>
                {report.job_release && (
                    <span className="text-xs text-gray-500 ml-1">· {report.job_release}</span>
                )}
            </div>

            {/* urgency tally */}
            <div className="flex flex-wrap gap-1.5">
                {URGENCY_ORDER.filter((k) => tally[k]).map((k) => {
                    const u = URGENCY_STYLES[k];
                    return (
                        <span key={k} className={`text-xs font-semibold px-2 py-1 rounded ${u.chip}`}>
                            <span className="font-mono">{tally[k]}</span> {TALLY_LABELS[k]}
                        </span>
                    );
                })}
            </div>

            {/* ranked findings */}
            {findings.length > 0 && (
                <div className="space-y-2">
                    {findings.map((f, i) => (
                        <RankedFinding
                            key={i}
                            f={f}
                            index={i}
                            releaseId={releaseId}
                            reviewId={reviewId}
                            feedback={feedback}
                        />
                    ))}
                </div>
            )}

            {/* cleared */}
            {cleared.length > 0 && (
                <details className="text-xs text-gray-600">
                    <summary className="cursor-pointer text-green-700 font-medium">
                        {cleared.length} cleared {cleared.length === 1 ? 'check' : 'checks'}
                    </summary>
                    <ul className="mt-1 space-y-0.5 pl-1">
                        {cleared.map((f, i) => (
                            <li key={i} className="flex gap-1.5">
                                <span className="text-green-600">✓</span>
                                <span className="font-mono text-gray-500">{f.rule_id}</span>
                                {f.issue && <span className="text-gray-600">— {f.issue}</span>}
                            </li>
                        ))}
                    </ul>
                </details>
            )}

            <div className="flex items-center gap-2 flex-wrap">
                {report.model && (
                    <p className="text-[11px] text-gray-400">🍌 Banana Boy · {report.model}</p>
                )}
                {canRerun && onRerun && (
                    <button
                        type="button"
                        onClick={onRerun}
                        disabled={rerunning}
                        className="ml-auto text-[11px] px-2.5 py-1 rounded bg-yellow-500 text-white font-semibold disabled:opacity-50"
                    >
                        {rerunning ? 'Re-running…' : '↻ Re-run BB review'}
                    </button>
                )}
            </div>
        </div>
    );
}

export default BBReviewReport;
