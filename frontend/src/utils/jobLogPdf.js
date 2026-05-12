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

const PRINT_WIDTH_OVERRIDES = {
    'Urgency': 4,
    'Stage': 7,
    'Description': 11,
    'Fab Order': 4,
    'Comp. ETA': 4,
    'Job': 10,
    'Notes': 8,
};

const DATE_COLUMNS = new Set(['Released', 'Start install', 'Comp. ETA']);

const COLOR_GRAYED = [156, 163, 175];
const COLOR_EVEN_ROW = [219, 234, 254];
const COLOR_HARD_DATE = [239, 68, 68];
const COLOR_HEAD_FILL = [224, 224, 224];
const COLOR_HEAD_LINE = [153, 153, 153];
const COLOR_BODY_LINE = [204, 204, 204];

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
    const raw = job[column];
    const value = DATE_COLUMNS.has(column)
        ? formatDateShort(raw)
        : formatCellValue(raw, column);
    return String(value || '—');
}

// Build a parallel rowMeta array (indexed by data.row.index) that the
// didParseCell / didDrawCell hooks read for coloring + Urgency rendering.
function buildRows(jobs, columnHeaders) {
    const body = [];
    const meta = [];
    for (const job of jobs) {
        const isInstallComplete = (job['Job Comp'] || '').toString().trim().toUpperCase() === 'X';
        const isGrayed = isInstallComplete || isCompleteStage(job['Stage']);
        meta.push({
            isGrayed,
            stage: job['Stage'] || 'Released',
            startInstallHard:
                job['start_install_formulaTF'] === false && Boolean(job['Start install']),
        });
        body.push(columnHeaders.map((col) => formatCell(job, col)));
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
    const head = [columnHeaders.map((col) => HEADER_OVERRIDES[col] ?? col)];

    const doc = new jsPDF({
        orientation: 'landscape',
        unit: 'pt',
        format: [PAGE_WIDTH_PT, PAGE_HEIGHT_PT],
    });

    const tableTopY = MARGIN_PT;
    const startInstallIdx = columnHeaders.indexOf('Start install');
    const urgencyIdx = columnHeaders.indexOf('Urgency');

    pmGroups.forEach(({ rows: pmRows }, groupIdx) => {
        if (groupIdx > 0) doc.addPage();
        const startPage = doc.internal.getNumberOfPages();
        const { body, meta } = buildRows(pmRows, columnHeaders);

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

                if (rowMeta.isGrayed) {
                    data.cell.styles.fillColor = COLOR_GRAYED;
                } else if (data.row.index % 2 === 1) {
                    data.cell.styles.fillColor = COLOR_EVEN_ROW;
                }

                if (data.column.index === startInstallIdx && rowMeta.startInstallHard) {
                    data.cell.styles.fillColor = COLOR_HARD_DATE;
                    data.cell.styles.textColor = 255;
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
