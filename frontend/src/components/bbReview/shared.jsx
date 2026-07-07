/**
 * The shared BB-review finding card: verdict + severity + issue + worked math + the
 * sheet-cited values. Used by both the admin per-version panel (BBReviewPanel) and the
 * PM report (BBReviewReport). Urgency helpers live alongside in ./urgency.js.
 */
import React from 'react';

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

export default Finding;
