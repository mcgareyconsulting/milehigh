/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Tells you a release has photos on it without opening the release hub —
 *   a small camera glyph rendered beside the Description in the Job Log row and card.
 * exports:
 *   PhotoBadge: <PhotoBadge count={number} className={string} />
 * imports_from: [react]
 * imported_by: [./JobsTableRow.jsx, ./JobLogCard.jsx]
 * notes:
 *   - count 0/null → renders nothing, so a release without photos costs no ink
 *   - the count itself stays in the tooltip; the row already carries enough numbers
 *   - drawn in currentColor so the caller decides how loud it is
 */
import React from 'react';

export function PhotoBadge({ count = 0, className = '' }) {
    const n = Number(count) || 0;
    if (n < 1) return null;
    const label = n === 1 ? '1 photo attached' : `${n} photos attached`;

    return (
        <svg
            viewBox="0 0 24 24"
            width="13"
            height="13"
            role="img"
            aria-label={label}
            className={`inline-block flex-shrink-0 ${className}`}
            style={{ verticalAlign: '-2px' }}
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
        >
            <title>{label}</title>
            <path d="M4 8.5h3l1.4-2h7.2l1.4 2h3a1 1 0 0 1 1 1V18a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9.5a1 1 0 0 1 1-1Z" />
            <circle cx="12" cy="13.4" r="3.1" />
        </svg>
    );
}

export default PhotoBadge;
