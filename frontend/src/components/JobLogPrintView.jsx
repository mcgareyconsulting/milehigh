import React, { useEffect, useMemo, useRef } from 'react';
import { isCompleteStage, getBananaProgress } from '../utils/stageProgress';
import { formatDateShort, formatCellValue } from '../utils/formatters';
import { BananaIcon } from './BananaIcon';
import './JobLogPrintView.css';

// 7.5in printable height (8.5in page − 0.5in margins × 2) at 96 CSS px/in.
// SAFETY_PX absorbs hairline borders and sub-pixel rounding so a row that
// measures within ~6px of the bottom doesn't get wrongly fit onto the page.
const PAGE_HEIGHT_PX = 720;
const PAGE_SAFETY_PX = 6;
const PRINT_TABLE_WIDTH_PX = 1248; // 13in × 96dpi
const MEASURE_STYLE_ID = 'job-log-print-measure';

const PRINT_BANANA_WIDTH = 90;
const PRINT_BANANA_HEIGHT = 28;

const PRINT_WIDTH_OVERRIDES = {
    'Urgency': 8,
    'Description': 10,
    'Fab Order': 4,
    'Comp. ETA': 4,
};

const HEADER_LABELS = {
    'Release #': 'rel. #',
    'Job Comp': 'Install Prog',
};

const DATE_COLUMNS = new Set(['Released', 'Start install', 'Comp. ETA']);

function PrintRow({ job, columnHeaders }) {
    const isInstallComplete = (job['Job Comp'] || '').toString().trim().toUpperCase() === 'X';
    const isGrayed = isInstallComplete || isCompleteStage(job['Stage']);

    return (
        <tr className={isGrayed ? 'grayed-row' : undefined}>
            {columnHeaders.map((column) => {
                if (column === 'Urgency') {
                    return (
                        <td key={column} className="urgency-cell">
                            <BananaIcon
                                progress={getBananaProgress(job['Stage'] || 'Released')}
                                width={PRINT_BANANA_WIDTH}
                                height={PRINT_BANANA_HEIGHT}
                            />
                        </td>
                    );
                }

                const raw = job[column];
                const value = DATE_COLUMNS.has(column)
                    ? formatDateShort(raw)
                    : formatCellValue(raw, column);
                const display = String(value || '—');
                const isHardDate =
                    column === 'Start install' &&
                    job['start_install_formulaTF'] === false &&
                    job['Start install'];

                return (
                    <td key={column} className={isHardDate ? 'hard-date' : undefined}>
                        {display}
                    </td>
                );
            })}
        </tr>
    );
}

function PMSection({ pm, rows, columnHeaders, colgroupCols }) {
    return (
        <section className="pm-section">
            <div className="pm-header">PM: {pm}</div>
            <table>
                <colgroup>
                    {colgroupCols.map((pct, i) => (
                        <col key={i} style={{ width: `${pct}%` }} />
                    ))}
                </colgroup>
                <thead>
                    <tr>
                        {columnHeaders.map((col) => (
                            <th key={col}>{HEADER_LABELS[col] ?? col}</th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {rows.map((job, idx) => (
                        <PrintRow
                            key={`${job['Job #'] ?? 'x'}-${job['Release #'] ?? idx}-${idx}`}
                            job={job}
                            columnHeaders={columnHeaders}
                        />
                    ))}
                </tbody>
            </table>
        </section>
    );
}

const MEASURE_STYLE = `
    .job-log-print-only {
        display: block !important;
        position: absolute !important;
        left: -99999px !important;
        top: 0 !important;
        width: ${PRINT_TABLE_WIDTH_PX}px !important;
        visibility: hidden !important;
        font-family: Arial, sans-serif !important;
        font-size: 10px !important;
    }
    .job-log-print-only .pm-header { font-size: 14px; font-weight: bold; margin: 0 0 8px; padding: 6px 8px; border-bottom: 2px solid #333; }
    .job-log-print-only table { width: 100%; border-collapse: collapse; margin-bottom: 12px; table-layout: fixed; }
    .job-log-print-only th { border: 1px solid #999; padding: 6px 4px; font-weight: bold; font-size: 9px; }
    .job-log-print-only td { border: 1px solid #ccc; padding: 6px 4px; font-size: 9px; }
    .job-log-print-only td.urgency-cell { padding: 2px 4px; }
`;

// Predict how many printed pages a .pm-section will consume, by simulating
// what Chrome does: each row is kept whole (`tr { break-inside: avoid }`),
// thead repeats on continuation pages (`display: table-header-group`), and
// page 1 has the .pm-header above the table. Replaces the prior division
// approximation, which overcounted when slack was < the assumed 60px and
// caused unnecessary blank pages to be inserted between PMs.
function predictPrintPages(section) {
    const pmHeader = section.querySelector('.pm-header');
    const thead = section.querySelector('thead');
    const rows = section.querySelectorAll('tbody tr');
    if (!rows.length) return 1;

    const pmHeaderH = pmHeader ? pmHeader.getBoundingClientRect().height : 0;
    const theadH = thead ? thead.getBoundingClientRect().height : 0;
    const limit = PAGE_HEIGHT_PX - PAGE_SAFETY_PX;

    let pages = 1;
    let pageY = pmHeaderH + theadH;
    for (const row of rows) {
        const rowH = row.getBoundingClientRect().height;
        if (pageY + rowH > limit && pageY > theadH) {
            pages += 1;
            pageY = theadH;
        }
        pageY += rowH;
    }
    return pages;
}

export default function JobLogPrintView({ jobs, columnHeaders, columnWidthPercent }) {
    const rootRef = useRef(null);

    const colgroupCols = useMemo(() => {
        const defaultWeight = 5;
        const weightFor = (col) =>
            PRINT_WIDTH_OVERRIDES[col] ?? columnWidthPercent[col] ?? defaultWeight;
        const total = columnHeaders.reduce((sum, col) => sum + weightFor(col), 0);
        return columnHeaders.map((col) => ((weightFor(col) / total) * 100).toFixed(2));
    }, [columnHeaders, columnWidthPercent]);

    const pmGroups = useMemo(() => {
        const groups = [];
        const byPM = new Map();
        for (const job of jobs) {
            const pm = job['PM'] || 'No PM';
            let entry = byPM.get(pm);
            if (!entry) {
                entry = { pm, rows: [] };
                byPM.set(pm, entry);
                groups.push(entry);
            }
            entry.rows.push(job);
        }
        return groups;
    }, [jobs]);

    // Recto alignment is enforced at print time: measure each PM section's
    // height at print width, predict which physical page each PM lands on, and
    // inject a blank verso filler before any PM that would otherwise start on
    // the back of a sheet. (Chrome's print engine doesn't reliably honor
    // `break-before: right` for multi-page tables, so we do it ourselves.)
    useEffect(() => {
        const beforePrint = () => {
            const root = rootRef.current;
            if (!root) return;

            root.querySelectorAll('.recto-filler').forEach((f) => f.remove());
            document.getElementById(MEASURE_STYLE_ID)?.remove();

            const emu = document.createElement('style');
            emu.id = MEASURE_STYLE_ID;
            emu.textContent = MEASURE_STYLE;
            document.head.appendChild(emu);

            try {
                const sections = Array.from(root.querySelectorAll('.pm-section'));
                let currentPage = 1;
                const fillerTargets = [];

                sections.forEach((sec, idx) => {
                    const pages = predictPrintPages(sec);
                    // currentPage is the page where this PM will start. If even
                    // (verso/back of sheet), insert a filler so it lands on a
                    // recto (front of sheet) instead.
                    if (idx > 0 && currentPage % 2 === 0) {
                        fillerTargets.push(sec);
                        currentPage += 1;
                    }
                    currentPage += pages;
                });

                fillerTargets.forEach((sec) => {
                    const filler = document.createElement('div');
                    filler.className = 'recto-filler';
                    sec.parentNode.insertBefore(filler, sec);
                });
            } finally {
                emu.remove();
            }
        };

        const afterPrint = () => {
            rootRef.current?.querySelectorAll('.recto-filler').forEach((f) => f.remove());
        };

        window.addEventListener('beforeprint', beforePrint);
        window.addEventListener('afterprint', afterPrint);
        return () => {
            window.removeEventListener('beforeprint', beforePrint);
            window.removeEventListener('afterprint', afterPrint);
        };
    }, []);

    return (
        <div ref={rootRef} className="job-log-print-only" aria-hidden="true">
            {pmGroups.map(({ pm, rows }) => (
                <PMSection
                    key={pm}
                    pm={pm}
                    rows={rows}
                    columnHeaders={columnHeaders}
                    colgroupCols={colgroupCols}
                />
            ))}
        </div>
    );
}
