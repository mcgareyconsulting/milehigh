/**
 * BBReviewReport — the PM-facing report for one release, rendered from the server's
 * assembled report object (app/brain/pdf_review/report.build_report):
 *   { headline, hold_recommended, tally, findings: [<f + urgency>], cleared: [...] }
 *
 * Verdict banner + urgency tally + findings ranked most-urgent-first (severity stripe +
 * urgency pill + the shared Finding detail) + a compact cleared list. Read-only.
 */
import React from 'react';

import { Finding } from './shared';
import { URGENCY_STYLES, URGENCY_ORDER } from './urgency';

const TALLY_LABELS = {
    critical: 'Critical', high: 'High', moderate: 'Moderate', low: 'Low', cleared: 'Cleared',
};

function RankedFinding({ f }) {
    const u = URGENCY_STYLES[f.urgency] || URGENCY_STYLES.low;
    return (
        <div className={`border-l-4 ${u.stripe} pl-2`}>
            <div className="flex items-center gap-2 mb-1">
                <span className={`text-[10px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded ${u.chip}`}>
                    {u.label}
                </span>
                {f.rule_id && <span className="text-[10px] text-gray-400 font-mono">{f.rule_id}</span>}
            </div>
            <Finding f={f} />
        </div>
    );
}

export function BBReviewReport({ report }) {
    if (!report) return null;
    const { headline, hold_recommended, tally = {}, findings = [], cleared = [] } = report;

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
                    {findings.map((f, i) => <RankedFinding key={i} f={f} />)}
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

            {report.model && (
                <p className="text-[11px] text-gray-400">🍌 Banana Boy · {report.model}</p>
            )}
        </div>
    );
}

export default BBReviewReport;
