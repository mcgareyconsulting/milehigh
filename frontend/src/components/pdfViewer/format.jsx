/**
 * Shared formatting for the hybrid PDF viewer (dates, file sizes, @mention bodies).
 * Lifted from the retired PdfVersionHistoryModal so the pane, the dock and the
 * stage-photo gate all render a version row the same way.
 */
import React from 'react';

export const fmtDate = (iso) => {
    if (!iso) return '—';
    try {
        return new Date(iso).toLocaleString();
    } catch {
        return iso;
    }
};

export const fmtSize = (bytes) => {
    if (!bytes) return '';
    const kb = bytes / 1024;
    if (kb < 1024) return `${kb.toFixed(0)} KB`;
    return `${(kb / 1024).toFixed(1)} MB`;
};

/** Render @FirstName mentions in bold accent (mirrors board comment rendering). */
export function renderCommentBody(body) {
    return (body || '').split(/(@\w+)/g).map((part, i) =>
        part.startsWith('@')
            ? <span key={i} className="font-semibold text-accent-500">{part}</span>
            : part
    );
}
