/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Builds a paginated, per-PM tabloid-landscape PDF of the Job Log Review tab. Each PM block starts on a fresh page and non-final PMs are padded to even page count so subsequent PMs land on the recto when printed double-sided.
 * exports:
 *   generateJobLogReviewPdf: async ({ jobs, columnHeaders, columnWidthPercent }) → triggers PDF download
 * imports_from: [jspdf, jspdf-autotable, ./formatters, ./stageProgress]
 * imported_by: [pages/JobLog.jsx]
 * invariants:
 *   - Page format is tabloid landscape (17in x 11in = 1224pt x 792pt)
 *   - Each PM section starts on a fresh page; non-final PMs are padded to even page count
 *   - Urgency cells render a rasterized 7-icon Banana Code row keyed by stage name
 */
import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';
import { formatDateShort, formatCellValue } from './formatters';
import {
    isCompleteStage,
    isHoldStage,
    DEPARTMENTS,
    ICON_STATES,
    getStageIconRow,
} from './stageProgress';
import {
    HOLD_FLAG_VIEWBOX,
    HOLD_FLAG_COLORS,
    HOLD_FLAG_POLE,
    HOLD_FLAG_POINTS,
    HOLD_FLAG_STROKE_WIDTH,
} from './holdFlag';
import { HEADER_OVERRIDES } from '../constants/columnHeaders';
import { DATE_COLUMNS } from './jobLogColumns';

const PAGE_WIDTH_PT = 1224;
const PAGE_HEIGHT_PT = 792;
const MARGIN_PT = 36;

// Banana Code icon row — 7 dept icons rendered into the Urgency cell.
// 3× DPI so the embedded PNG stays crisp on print. Fixed draw height keeps
// per-row icon size identical (so the 7-icon row doesn't wobble between rows).
const ICON_DPI_SCALE = 3;
const ICON_ROW_DRAW_HEIGHT_PT = 12;

// Cap wrapped text at this many lines per cell; further wrapping is replaced
// with an ellipsis on the last kept line.
const MAX_LINES_PER_CELL = 2;

// Floor every body row at the natural height of a 2-line cell so all rows print
// at a uniform height (single-line rows grow to match wrapped ones).
const BODY_FONT_SIZE = 9;          // matches styles.fontSize
const LINE_HEIGHT_RATIO = 1.15;    // jspdf-autotable FONT_ROW_RATIO
const CELL_PAD_V = 1.5;            // body cellPadding top == bottom
const CELL_PAD_H = 3;             // body cellPadding left == right
const TWO_LINE_MIN_HEIGHT_PT =
    MAX_LINES_PER_CELL * BODY_FONT_SIZE * LINE_HEIGHT_RATIO + CELL_PAD_V * 2;

// Print-only header label overrides (the column key/data field is unchanged).
// Kept separate from the shared HEADER_OVERRIDES so this doesn't rename the
// on-screen Job Log / Archive table headers.
const PRINT_HEADER_OVERRIDES = {
    'Urgency': 'Banana Code',
};

const PRINT_WIDTH_OVERRIDES = {
    'Urgency': 6,
    'Stage': 5,
    'Description': 11,
    'Fab Order': 4,
    'Comp. ETA': 4,
    'Job': 10,
    'Notes': 8,
};


const COLOR_GRAYED = [156, 163, 175];
const COLOR_EVEN_ROW = [219, 234, 254];
// Start install hard-date states — mirror the on-screen Tailwind shades in
// JobsTableRow.jsx (bg-red-500 / bg-green-500 / bg-yellow-400, text-gray-900).
const COLOR_ASAP = [239, 68, 68];          // bg-red-500
const COLOR_HARD_FUTURE = [34, 197, 94];   // bg-green-500
const COLOR_HARD_PAST = [250, 204, 21];    // bg-yellow-400
const COLOR_HARD_PAST_TEXT = [17, 24, 39]; // text-gray-900
const COLOR_HEAD_FILL = [224, 224, 224];
const COLOR_HEAD_LINE = [40, 40, 40];
const COLOR_BODY_LINE = [40, 40, 40];

// Stage → stage_group → fill/text RGB. Mirrors useJobsFilters.js:478-506 so the
// printed Stage cell carries the same color signal as the in-app dropdown.
const STAGE_TO_GROUP = {
    'Released': 'FABRICATION',
    'Material Ordered': 'FABRICATION',
    'Cut Start': 'FABRICATION',
    'Cut Complete': 'FABRICATION',
    'Fitup Start': 'FABRICATION',
    'Fitup Complete': 'FABRICATION',
    'Weld Start': 'FABRICATION',
    'Weld Complete': 'FABRICATION',
    'Hold': 'FABRICATION',
    'Welded QC': 'READY_TO_SHIP',
    'Paint Start': 'READY_TO_SHIP',
    'Paint Complete': 'READY_TO_SHIP',
    'Store at MHMW': 'READY_TO_SHIP',
    'Ship Planning': 'READY_TO_SHIP',
    'Ship Complete': 'COMPLETE',
    'Install Start': 'COMPLETE',
    'Install Complete': 'COMPLETE',
    'Complete': 'COMPLETE',
};
const STAGE_GROUP_COLORS = {
    FABRICATION:   { fill: [219, 234, 254], text: [30, 64, 175] },
    READY_TO_SHIP: { fill: [209, 250, 229], text: [6, 95, 70] },
    COMPLETE:      { fill: [237, 233, 254], text: [91, 33, 182] },
};

function loadImage(src) {
    return new Promise((resolve, reject) => {
        const img = new Image();
        img.onload = () => resolve(img);
        img.onerror = reject;
        img.src = src;
    });
}

// Load all 28 dept × state icon images once and cache the decoded HTMLImageElement
// map for the lifetime of the page. Re-exporting the same PDF reuses the cache.
let _iconAssetsPromise = null;
function getIconAssets() {
    if (!_iconAssetsPromise) {
        const entries = [];
        for (const dept of DEPARTMENTS) {
            for (const state of ICON_STATES) {
                const key = `${dept}_${state}`;
                entries.push(loadImage(`/icons/${key}.png`).then((img) => [key, img]));
            }
        }
        _iconAssetsPromise = Promise.all(entries).then(Object.fromEntries);
    }
    return _iconAssetsPromise;
}

// Render the seven dept icons for a given stage into a row PNG. Source PNGs
// are 2:3 portrait, so we render each icon at that aspect ratio centered in
// its slot. Smooth interpolation (imageSmoothingEnabled=true) is what these
// illustration assets want — pixelated rendering hard-edges the curves.
const ICON_ASPECT_W_OVER_H = 2 / 3;

function buildIconRowPng(iconAssets, stage, canvasW, canvasH) {
    const canvas = document.createElement('canvas');
    canvas.width = canvasW;
    canvas.height = canvasH;
    const ctx = canvas.getContext('2d');
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'high';

    const row = getStageIconRow(stage);
    const slotW = canvasW / DEPARTMENTS.length;
    const iconH = canvasH;
    const iconW = Math.min(slotW, iconH * ICON_ASPECT_W_OVER_H);

    DEPARTMENTS.forEach((dept, i) => {
        const state = row[i];
        const img = iconAssets[`${dept}_${state}`];
        const xOffset = i * slotW + (slotW - iconW) / 2;
        if (img) ctx.drawImage(img, xOffset, 0, iconW, iconH);
    });

    if (isHoldStage(stage)) {
        const weldIdx = DEPARTMENTS.indexOf('weld');
        const slotX = weldIdx * slotW + (slotW - iconW) / 2;
        drawHoldFlag(ctx, slotX + iconW, 0, iconW);
    }

    return canvas.toDataURL('image/png');
}

function drawHoldFlag(ctx, anchorX, anchorY, iconSize) {
    const flagH = Math.max(6, iconSize * 0.55);
    const flagW = flagH;
    const x = anchorX - flagW * 0.65;
    const y = anchorY - flagH * 0.15;
    ctx.save();
    ctx.translate(x, y);
    ctx.scale(flagW / HOLD_FLAG_VIEWBOX, flagH / HOLD_FLAG_VIEWBOX);
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';

    ctx.strokeStyle = HOLD_FLAG_COLORS.pole;
    ctx.lineWidth = HOLD_FLAG_POLE.width;
    ctx.beginPath();
    ctx.moveTo(HOLD_FLAG_POLE.x1, HOLD_FLAG_POLE.y1);
    ctx.lineTo(HOLD_FLAG_POLE.x2, HOLD_FLAG_POLE.y2);
    ctx.stroke();

    ctx.fillStyle = HOLD_FLAG_COLORS.fill;
    ctx.strokeStyle = HOLD_FLAG_COLORS.stroke;
    ctx.lineWidth = HOLD_FLAG_STROKE_WIDTH;
    ctx.beginPath();
    HOLD_FLAG_POINTS.forEach(([px, py], i) => {
        if (i === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
    });
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
    ctx.restore();
}

// Returns a getter that lazily produces a per-(stage, w) icon-row PNG at a
// FIXED draw height. Within the Urgency column the cell width is constant, so
// this collapses to one PNG per unique stage value.
function makeIconRowProvider(iconAssets) {
    const cache = new Map();
    const hPx = Math.max(2, Math.round(ICON_ROW_DRAW_HEIGHT_PT * ICON_DPI_SCALE));
    return (stage, drawWPt) => {
        const wPx = Math.max(2, Math.round(drawWPt * ICON_DPI_SCALE));
        const key = `${stage}|${wPx}`;
        let png = cache.get(key);
        if (!png) {
            png = buildIconRowPng(iconAssets, stage, wPx, hPx);
            cache.set(key, png);
        }
        return png;
    };
}

function groupByPm(jobs) {
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
}

function buildColumnStyles(columnHeaders, columnWidthPercent) {
    const printableWidth = PAGE_WIDTH_PT - MARGIN_PT * 2;
    const defaultWeight = 5;
    const weightFor = (col) =>
        PRINT_WIDTH_OVERRIDES[col] ?? columnWidthPercent[col] ?? defaultWeight;
    const total = columnHeaders.reduce((sum, col) => sum + weightFor(col), 0);

    const styles = {};
    columnHeaders.forEach((col, i) => {
        styles[i] = { cellWidth: (weightFor(col) / total) * printableWidth };
    });
    return styles;
}

function formatCell(job, column) {
    if (column === 'Urgency') return '';
    // ASAP rows show the literal "ASAP" instead of a (usually empty) date,
    // matching the on-screen displayValue in JobsTableRow.jsx.
    if (column === 'Start install' && job['start_install_asap'] === true) return 'ASAP';
    const raw = job[column];
    const value = DATE_COLUMNS.has(column)
        ? formatDateShort(raw)
        : formatCellValue(raw, column);
    return String(value || '—');
}

// Hard-cap a cell's text to MAX_LINES_PER_CELL lines based on the actual column
// width, ellipsizing the last kept line. autotable's own width-wrapping happens
// after didParseCell, so capping there only catches explicit newlines — long
// values (e.g. Notes) still wrap to 3+ lines and grow the row. Pre-truncating
// here guarantees every row stays at the uniform two-line height. The font must
// be set to match the body style before calling (done in buildRows).
function truncateToTwoLines(doc, text, innerWidth) {
    const str = String(text ?? '');
    if (!str || innerWidth <= 0) return str;
    const lines = doc.splitTextToSize(str, innerWidth);
    if (lines.length <= MAX_LINES_PER_CELL) return lines.join('\n');
    const kept = lines.slice(0, MAX_LINES_PER_CELL);
    const ellipsis = '…';
    let last = kept[kept.length - 1];
    while (last.length > 0 && doc.getTextWidth(last + ellipsis) > innerWidth) {
        last = last.slice(0, -1);
    }
    kept[kept.length - 1] = last.replace(/\s+$/, '') + ellipsis;
    return kept.join('\n');
}

// Resolve the Start install hard-date state for coloring. Mirrors the on-screen
// logic in JobsTableRow.jsx:1148-1171: ASAP > past hard date > future/today hard
// date. Formula-driven dates return null (no special fill). The past comparison
// uses the LOCAL date (toISOString would shift to UTC).
function startInstallState(job) {
    if (job['start_install_asap'] === true) return 'asap';
    // A no-color date (auto-recorded when an ASAP release reached Ship Complete+)
    // shows the date plainly — mirror JobsTableRow.jsx so print matches the screen.
    const isNoColor = job['start_install_no_color'] === true;
    const isHardDate =
        !isNoColor && job['start_install_formulaTF'] === false && Boolean(job['Start install']);
    if (!isHardDate) return null;
    const now = new Date();
    const todayStr =
        `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-` +
        `${String(now.getDate()).padStart(2, '0')}`;
    const installDay = String(job['Start install'] ?? '').split('T')[0];
    return installDay < todayStr ? 'hardPast' : 'hardFuture';
}

// Build a parallel rowMeta array (indexed by data.row.index) that the
// didParseCell / didDrawCell hooks read for coloring + Urgency rendering.
// innerWidths[i] is the usable text width (pt) of column i, used to pre-cap
// cell text to two lines so all rows share the same height.
function buildRows(jobs, columnHeaders, doc, innerWidths) {
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(BODY_FONT_SIZE);
    const body = [];
    const meta = [];
    for (const job of jobs) {
        const isInstallComplete = (job['Job Comp'] || '').toString().trim().toUpperCase() === 'X';
        const isGrayed = isInstallComplete || isCompleteStage(job['Stage']);
        meta.push({
            isGrayed,
            stage: job['Stage'] || 'Released',
            startInstallState: startInstallState(job),
        });
        body.push(columnHeaders.map(
            (col, i) => truncateToTwoLines(doc, formatCell(job, col), innerWidths[i]),
        ));
    }
    return { body, meta };
}

function timestampStr() {
    const now = new Date();
    const pad = (n) => String(n).padStart(2, '0');
    return (
        `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}` +
        `-${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`
    );
}

export async function generateJobLogReviewPdf({ jobs, columnHeaders, columnWidthPercent }) {
    if (!jobs || jobs.length === 0) {
        alert('No data to export');
        return;
    }

    const iconAssets = await getIconAssets();
    const iconRowProvider = makeIconRowProvider(iconAssets);
    const pmGroups = groupByPm(jobs);
    const columnStyles = buildColumnStyles(columnHeaders, columnWidthPercent);
    // Usable text width per column (cell width minus L/R padding). The extra 1pt
    // margin makes our wrap slightly more aggressive than autotable's so it never
    // produces an extra line beyond what we measured here.
    const innerWidths = columnHeaders.map(
        (_, i) => columnStyles[i].cellWidth - CELL_PAD_H * 2 - 1,
    );
    const head = [columnHeaders.map(
        (col) => PRINT_HEADER_OVERRIDES[col] ?? HEADER_OVERRIDES[col] ?? col,
    )];

    const doc = new jsPDF({
        orientation: 'landscape',
        unit: 'pt',
        format: [PAGE_WIDTH_PT, PAGE_HEIGHT_PT],
    });

    const tableTopY = MARGIN_PT;
    const startInstallIdx = columnHeaders.indexOf('Start install');
    const urgencyIdx = columnHeaders.indexOf('Urgency');
    const stageIdx = columnHeaders.indexOf('Stage');

    pmGroups.forEach(({ rows: pmRows }, groupIdx) => {
        if (groupIdx > 0) doc.addPage();
        const startPage = doc.internal.getNumberOfPages();
        const { body, meta } = buildRows(pmRows, columnHeaders, doc, innerWidths);

        autoTable(doc, {
            head,
            body,
            startY: tableTopY,
            margin: { top: tableTopY, left: MARGIN_PT, right: MARGIN_PT, bottom: MARGIN_PT },
            theme: 'grid',
            showHead: 'everyPage',
            rowPageBreak: 'avoid',
            styles: {
                font: 'helvetica',
                fontSize: 9,
                cellPadding: { top: 1.5, bottom: 1.5, left: 3, right: 3 },
                textColor: 0,
                lineColor: COLOR_BODY_LINE,
                lineWidth: 0.5,
                halign: 'center',
                valign: 'middle',
                overflow: 'linebreak',
            },
            headStyles: {
                fillColor: COLOR_HEAD_FILL,
                textColor: 0,
                fontStyle: 'bold',
                fontSize: 9.5,
                cellPadding: { top: 2, bottom: 2, left: 3, right: 3 },
                lineColor: COLOR_HEAD_LINE,
                lineWidth: 0.5,
            },
            bodyStyles: {
                minCellHeight: TWO_LINE_MIN_HEIGHT_PT,
            },
            columnStyles,
            didParseCell: (data) => {
                if (data.section !== 'body') return;

                // Cap wrap at MAX_LINES_PER_CELL; ellipsize the last kept line
                // when the original wrap produced more than that.
                if (Array.isArray(data.cell.text) && data.cell.text.length > MAX_LINES_PER_CELL) {
                    const kept = data.cell.text.slice(0, MAX_LINES_PER_CELL);
                    const lastIdx = kept.length - 1;
                    const last = kept[lastIdx] ?? '';
                    kept[lastIdx] = last.length > 1 ? last.slice(0, -1).trimEnd() + '…' : '…';
                    data.cell.text = kept;
                }

                const rowMeta = meta[data.row.index];
                if (!rowMeta) return;

                // Stage cell carries its group color regardless of grayed/even-row tint.
                if (data.column.index === stageIdx) {
                    const palette = STAGE_GROUP_COLORS[STAGE_TO_GROUP[rowMeta.stage]];
                    if (palette) {
                        data.cell.styles.fillColor = palette.fill;
                        data.cell.styles.textColor = palette.text;
                        data.cell.styles.fontStyle = 'bold';
                        return;
                    }
                }

                if (rowMeta.isGrayed) {
                    data.cell.styles.fillColor = COLOR_GRAYED;
                } else if (data.row.index % 2 === 1) {
                    data.cell.styles.fillColor = COLOR_EVEN_ROW;
                }

                if (data.column.index === startInstallIdx && rowMeta.startInstallState) {
                    if (rowMeta.startInstallState === 'asap') {
                        data.cell.styles.fillColor = COLOR_ASAP;
                        data.cell.styles.textColor = 255;
                    } else if (rowMeta.startInstallState === 'hardPast') {
                        data.cell.styles.fillColor = COLOR_HARD_PAST;
                        data.cell.styles.textColor = COLOR_HARD_PAST_TEXT;
                    } else if (rowMeta.startInstallState === 'hardFuture') {
                        data.cell.styles.fillColor = COLOR_HARD_FUTURE;
                        data.cell.styles.textColor = 255;
                    }
                    data.cell.styles.fontStyle = 'bold';
                }
            },
            didDrawCell: (data) => {
                if (data.section !== 'body') return;
                if (data.column.index !== urgencyIdx) return;
                const rowMeta = meta[data.row.index];
                if (!rowMeta) return;

                const padX = 3;
                const drawW = data.cell.width - padX * 2;
                const drawH = Math.min(ICON_ROW_DRAW_HEIGHT_PT, data.cell.height - 2);
                if (drawW <= 0 || drawH <= 0) return;
                const png = iconRowProvider(rowMeta.stage, drawW);
                const drawX = data.cell.x + padX;
                const drawY = data.cell.y + (data.cell.height - drawH) / 2;
                doc.addImage(png, 'PNG', drawX, drawY, drawW, drawH);
            },
        });

        const isLastGroup = groupIdx === pmGroups.length - 1;
        if (!isLastGroup) {
            const endPage = doc.internal.getNumberOfPages();
            const pagesUsed = endPage - startPage + 1;
            if (pagesUsed % 2 === 1) doc.addPage();
        }
    });

    doc.save(`job-log-review-${timestampStr()}.pdf`);
}
