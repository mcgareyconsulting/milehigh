/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Sub-invoice billing math shared by the Subs → Invoice Paid table, plus
 *   CSV and PDF exports of whatever rows that table is currently showing.
 * exports:
 *   INSTALL_RATE_PER_HOUR: Sub install rate ($/hr)
 *   installBudget: Install Hrs -> budget dollars (null when unknown)
 *   estimatedBillable: Install Prog % x budget (null when either is unknown)
 *   fmtUsd: dollars or an em dash
 *   exportSubsInvoicesCsv: ({ releases, filterLabel }) -> triggers CSV download
 *   exportSubsInvoicesPdf: async ({ releases, filterLabel }) -> triggers PDF download
 * imports_from: [jspdf, jspdf-autotable, ./pdfFonts, ./formatters, ../components/JobDetailsBody]
 * imported_by: [pages/Subs.jsx]
 * invariants:
 *   - Exports are the on-screen rows as-is (the caller passes its filtered list);
 *     the only reshaping is Company + Crew columns in place of the installer grouping.
 *   - Company comes from the API row (`company`); Crew is the installer team name.
 *   - Budget / Est. Billable are derived here exactly as on screen, never stored.
 */
import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';
import { ensureTableFonts } from './pdfFonts';
import { formatCellValue } from './formatters';
import { formatInstallProg } from '../components/JobDetailsBody';

/** Sub install rate. Budget = Install Hrs x this. */
export const INSTALL_RATE_PER_HOUR = 55;

/** Install Hrs -> budget dollars. Null when hours are missing/non-numeric. */
export function installBudget(installHrs) {
    const n = Number(installHrs);
    if (installHrs == null || installHrs === '' || !Number.isFinite(n)) return null;
    return n * INSTALL_RATE_PER_HOUR;
}

/**
 * Job Log install progress (job_comp) as a 0–1 fraction for billing math.
 *   "90" / "90%" / "90.5%" -> 0.9 / 0.9 / 0.905
 *   "X"                    -> 1 (the Job Log's complete marker)
 *   blank / "O" / junk     -> null (unknown, not zero — caller renders an em dash)
 *
 * The percent sign is part of the stored value on real rows (job_comp is free
 * text typed on the Job Log, e.g. "90%"), so it has to be tolerated, not just
 * bare digits. Over-100 entries clamp to 100% — a release cannot bill more than
 * its budget on progress alone.
 */
function installProgFraction(jobComp) {
    if (jobComp == null || jobComp === false) return null;
    const s = String(jobComp).trim();
    if (!s || s.toUpperCase() === 'O') return null;
    if (s.toUpperCase() === 'X') return 1;
    const m = /^(\d+(?:\.\d+)?)\s*%?$/.exec(s);
    if (!m) return null;
    return Math.min(Number(m[1]) / 100, 1);
}

/** Budget earned so far: install progress % x budget. Null if either is unknown. */
export function estimatedBillable(jobComp, installHrs) {
    const budget = installBudget(installHrs);
    const fraction = installProgFraction(jobComp);
    if (budget == null || fraction == null) return null;
    return budget * fraction;
}

export const fmtUsd = (amount) =>
    amount == null
        ? '—'
        : amount.toLocaleString('en-US', {
              style: 'currency',
              currency: 'USD',
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
          });

const HEADERS = [
    'Company',
    'Crew',
    'Job',
    'Rel',
    'Job name',
    'Description',
    'Stage',
    'Start install',
    'Status',
    'Install Prog',
    'Install Hrs',
    'Budget',
    'Est. Billable',
    'Progress',
    'Invoice #',
    'Invoiced complete',
];

/** Company, then crew, then job/release — the order a per-sub report reads in. */
function sortForReport(releases) {
    return [...releases].sort((a, b) => {
        const c = (a.company || '~').localeCompare(b.company || '~');
        if (c !== 0) return c;
        const i = (a.installer || '').localeCompare(b.installer || '', undefined, { numeric: true });
        if (i !== 0) return i;
        if (a.job !== b.job) return a.job - b.job;
        return String(a.release).localeCompare(String(b.release), undefined, { numeric: true });
    });
}

/**
 * One row of plain values. `money` formats dollars; CSV passes raw numbers so a
 * spreadsheet can sum them, the PDF passes fmtUsd.
 */
function rowValues(r, { money, invoiceJoin }) {
    const budget = installBudget(r.install_hrs);
    const billable = estimatedBillable(r.job_comp, r.install_hrs);
    const hrs = formatCellValue(r.install_hrs, 'Install HRS');
    const numbers = (r.installer_invoice_numbers || '')
        .split(/\r?\n/)
        .map((s) => s.trim())
        .filter(Boolean)
        .join(invoiceJoin);
    return [
        r.company || '',
        r.installer || '',
        r.job ?? '',
        r.release ?? '',
        r.job_name || '',
        r.description || '',
        r.stage || '',
        r.start_install || '',
        r.is_archived ? 'Archived' : 'Live',
        formatInstallProg(r.job_comp) || '',
        hrs === '—' ? '' : hrs ?? '',
        money(budget),
        money(billable),
        r.installer_invoice_progress == null ? '' : `${r.installer_invoice_progress}%`,
        numbers,
        r.installer_invoice_paid ? 'Yes' : 'No',
    ];
}

function fileStamp() {
    const d = new Date();
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function fileSlug(filterLabel) {
    const slug = (filterLabel || '')
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-+|-+$/g, '')
        .slice(0, 60);
    return slug ? `sub-invoices-${slug}-${fileStamp()}` : `sub-invoices-${fileStamp()}`;
}

function csvCell(value) {
    const s = value == null ? '' : String(value);
    return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export function exportSubsInvoicesCsv({ releases, filterLabel }) {
    const rows = sortForReport(releases).map((r) =>
        rowValues(r, {
            money: (n) => (n == null ? '' : n.toFixed(2)),
            invoiceJoin: '; ',
        }),
    );
    const csv = [HEADERS, ...rows].map((row) => row.map(csvCell).join(',')).join('\r\n');
    // BOM so Excel reads "—" / accents as UTF-8.
    const blob = new Blob(['﻿', csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${fileSlug(filterLabel)}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
}

export async function exportSubsInvoicesPdf({ releases, filterLabel }) {
    // Tabloid landscape — 16 columns don't fit legibly on letter.
    const doc = new jsPDF({ orientation: 'landscape', unit: 'pt', format: 'tabloid' });
    const font = await ensureTableFonts(doc);
    const margin = 36;

    doc.setFont(font, 'bold');
    doc.setFontSize(16);
    doc.text('Sub Invoices', margin, margin + 8);
    doc.setFont(font, 'normal');
    doc.setFontSize(10);
    doc.setTextColor(90);
    const generated = new Date().toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
    });
    doc.text(
        `${filterLabel || 'All companies · All projects'}  ·  ${releases.length} release${
            releases.length === 1 ? '' : 's'
        }  ·  Generated ${generated}`,
        margin,
        margin + 24,
    );
    doc.setTextColor(0);

    const body = sortForReport(releases).map((r) =>
        rowValues(r, { money: fmtUsd, invoiceJoin: '\n' }),
    );

    // Right-align numbers; widths are fractions of the printable width.
    const widths = [11, 5, 3.5, 3, 9, 13, 6, 5.5, 4.5, 4.5, 4.5, 6, 6, 4.5, 7.5, 6.5];
    const printable = doc.internal.pageSize.getWidth() - margin * 2;
    const total = widths.reduce((s, w) => s + w, 0);
    const numericCols = new Set([10, 11, 12]);
    const columnStyles = Object.fromEntries(
        widths.map((w, i) => [
            i,
            {
                cellWidth: (w / total) * printable,
                halign: numericCols.has(i) ? 'right' : i >= 2 && i !== 4 && i !== 5 ? 'center' : 'left',
            },
        ]),
    );

    autoTable(doc, {
        head: [HEADERS],
        body,
        startY: margin + 36,
        margin: { left: margin, right: margin },
        styles: { font, fontSize: 8.5, cellPadding: 3, overflow: 'linebreak', valign: 'middle' },
        headStyles: { fillColor: [241, 243, 245], textColor: [60, 60, 60], fontStyle: 'bold', halign: 'center' },
        alternateRowStyles: { fillColor: [250, 250, 250] },
        columnStyles,
        didDrawPage: () => {
            const pageH = doc.internal.pageSize.getHeight();
            doc.setFont(font, 'normal');
            doc.setFontSize(8);
            doc.setTextColor(120);
            doc.text(`Page ${doc.getCurrentPageInfo().pageNumber}`, margin, pageH - 16);
            doc.setTextColor(0);
        },
    });

    doc.save(`${fileSlug(filterLabel)}.pdf`);
}
