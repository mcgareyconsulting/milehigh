/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Ambient BB-review status indicator — a small 🍌 glyph with a colored corner dot
 *   showing where a submittal stands against BB's code-review rules. Read-only, unobtrusive;
 *   meant to be glanced at while scanning Drafting Work Load rows/cards.
 * exports:
 *   BBStatusBadge: Props — status (bb_status string | null), className (optional wrapper classes).
 * imports_from: [react]
 * imported_by: [SubmittalRow.jsx, SubmittalCard.jsx, TableRow.jsx]
 * invariants:
 *   - Renders nothing when status is falsy (graceful fallback before the backend field lands).
 *   - Dot colors are STATE colors (good/warning/critical), independent of the app's navy accent.
 *   - The "reviewing" pulse respects prefers-reduced-motion (no animation when reduced).
 */
import React from 'react';

// bb_status -> dot color + tooltip. Only these five values render a badge.
const STATUS_META = {
    violation: {
        dot: 'bg-red-500',
        pulse: false,
        title: 'BB found a code violation — hold recommended',
    },
    needs_verify: {
        dot: 'bg-amber-500',
        pulse: false,
        title: 'BB flagged items to verify in the field',
    },
    clear: {
        dot: 'bg-green-500',
        pulse: false,
        title: "Reviewed clear against BB's rules",
    },
    reviewing: {
        dot: 'bg-amber-500',
        pulse: true,
        title: 'BB is reviewing…',
    },
    pulled: {
        dot: 'bg-slate-400',
        pulse: false,
        title: 'Drawing pulled, not yet reviewed',
    },
};

export function BBStatusBadge({ status, className = '' }) {
    const meta = status ? STATUS_META[status] : null;
    if (!meta) return null;

    // Ring color = the row/card surface so the dot reads on any background.
    const ring = 'ring-2 ring-white dark:ring-slate-800';

    return (
        <span
            className={`relative inline-flex shrink-0 items-center justify-center leading-none ${className}`}
            title={meta.title}
            aria-label={meta.title}
            role="img"
        >
            <span className="text-sm" aria-hidden="true">🍌</span>
            <span
                className={`absolute -top-0.5 -right-0.5 h-2 w-2 rounded-full ${ring} ${meta.dot}`}
                aria-hidden="true"
            >
                {meta.pulse && (
                    <span
                        className={`absolute inset-0 rounded-full ${meta.dot} opacity-75 motion-safe:animate-ping`}
                        aria-hidden="true"
                    />
                )}
            </span>
        </span>
    );
}

export default BBStatusBadge;
