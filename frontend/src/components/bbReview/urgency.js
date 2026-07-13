/**
 * BB-review urgency helpers (no JSX). Mirror of app/brain/pdf_review/report.py —
 * keep the two in sync. Shared by the admin panel (BBReviewPanel) and the PM report
 * (BBReviewReport) so urgency is computed one way everywhere.
 */

// Most-urgent first. Colors track the report design: oxide-red → orange → amber → slate.
export const URGENCY_ORDER = ['critical', 'high', 'moderate', 'low', 'cleared'];

export const URGENCY_STYLES = {
    critical: { label: 'Critical', stripe: 'border-l-red-500', chip: 'bg-red-100 text-red-700', text: 'text-red-700' },
    high: { label: 'High', stripe: 'border-l-orange-500', chip: 'bg-orange-100 text-orange-700', text: 'text-orange-700' },
    moderate: { label: 'Moderate', stripe: 'border-l-amber-500', chip: 'bg-amber-100 text-amber-700', text: 'text-amber-700' },
    low: { label: 'Low', stripe: 'border-l-slate-400', chip: 'bg-slate-100 text-slate-600', text: 'text-slate-600' },
    cleared: { label: 'Cleared', stripe: 'border-l-green-400', chip: 'bg-green-100 text-green-700', text: 'text-green-700' },
};

/** (verdict, severity) -> urgency bucket. Mirror of report.urgency_for. */
export function urgencyOf(f) {
    if (f?.verdict === 'violation') return 'critical';
    if (f?.verdict === 'ok') return 'cleared';
    return { high: 'high', medium: 'moderate', low: 'low' }[f?.severity] || 'low';
}

/** Count findings by urgency bucket. */
export function tally(findings = []) {
    const t = { critical: 0, high: 0, moderate: 0, low: 0, cleared: 0 };
    findings.forEach((f) => { t[urgencyOf(f)] += 1; });
    return t;
}

/** Number of findings the PM needs to act on (everything except cleared). */
export function actionableCount(findings = []) {
    const t = tally(findings);
    return t.critical + t.high + t.moderate + t.low;
}
