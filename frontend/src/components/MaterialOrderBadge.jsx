/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Status indicator for a release's material orders, shown in the Job Log
 *   "Mats" column: a small icon whose color + glyph signals the order state.
 * exports:
 *   MaterialOrderBadge: <MaterialOrderBadge status={'received'|'pending'|'overdue'|null} />
 * imports_from: [react]
 * imported_by: [./JobsTableRow.jsx]
 * notes:
 *   - status null → renders nothing (releases without orders stay non-obtrusive)
 *   - received = green check, pending = yellow clock, overdue = red circle-x
 */
import React from 'react';

// Per-status colors echo the Start install red/yellow/green cell treatment and the
// green/amber modal badges, so the whole Job Log reads as one system.
const COLORS = {
    received: '#22c55e', // green-500
    pending: '#eab308',  // yellow-500
    overdue: '#ef4444',  // red-500
};

const LABELS = {
    received: 'Materials received — all orders in',
    pending: 'Ordered — not yet received',
    overdue: 'Overdue — install date passed and parts still out',
};

// White glyph drawn on top of a filled colored circle (24×24 viewBox, r=10 face).
function Glyph({ status }) {
    if (status === 'received') {
        // check
        return <path d="M7 12.3l3.2 3.2L17 8.7" fill="none" stroke="#fff"
            strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />;
    }
    if (status === 'overdue') {
        // x
        return (
            <g fill="none" stroke="#fff" strokeWidth="2.2" strokeLinecap="round">
                <line x1="8.5" y1="8.5" x2="15.5" y2="15.5" />
                <line x1="15.5" y1="8.5" x2="8.5" y2="15.5" />
            </g>
        );
    }
    // pending — clock hands
    return (
        <g fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 7.5V12l3 1.8" />
        </g>
    );
}

export function MaterialOrderBadge({ status }) {
    const color = COLORS[status];
    if (!color) return null;

    return (
        <svg
            viewBox="0 0 24 24"
            width="16"
            height="16"
            role="img"
            aria-label={LABELS[status]}
        >
            <title>{LABELS[status]}</title>
            <circle cx="12" cy="12" r="10" fill={color} />
            <Glyph status={status} />
        </svg>
    );
}

export default MaterialOrderBadge;
