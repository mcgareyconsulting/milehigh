/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Minimal dependency-free CSV builder + browser download helper.
 * exports:
 *   toCsv: Build an RFC-4180-ish CSV string from headers + row arrays.
 *   downloadCsv: Build a CSV and trigger a browser download (UTF-8 with BOM for Excel).
 * imported_by: [frontend/src/pages/InvoicingReport.jsx]
 */

function escapeCell(value) {
    const s = value == null ? '' : String(value);
    // Quote cells containing a comma, quote, or newline; double embedded quotes.
    return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export function toCsv(headers, rows) {
    const lines = [headers.map(escapeCell).join(',')];
    for (const row of rows) lines.push(row.map(escapeCell).join(','));
    return lines.join('\r\n');
}

export function downloadCsv(filename, headers, rows) {
    const csv = toCsv(headers, rows);
    // Leading BOM so Excel detects UTF-8.
    const blob = new Blob(['﻿', csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}
