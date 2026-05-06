/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Builds a paginated, per-PM legal-landscape PDF of the Job Log Review tab. Each PM block starts on a fresh page and non-final PMs are padded to even page count so subsequent PMs land on the recto when printed double-sided.
 * exports:
 *   generateJobLogReviewPdf: async ({ jobs, columnHeaders, columnWidthPercent }) → triggers PDF download
 * imports_from: [jspdf, jspdf-autotable, ./formatters, ./stageProgress]
 * imported_by: [pages/JobLog.jsx]
 * invariants:
 *   - Page format is legal landscape (14in x 8.5in = 1008pt x 612pt)
 *   - Each PM section starts on a fresh page; non-final PMs are padded to even page count
 *   - Urgency cells render rasterized BananaIcon canvases keyed by stage progress
 */
import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';
import { formatDateShort, formatCellValue } from './formatters';
import { isCompleteStage, getBananaProgress } from './stageProgress';

const PAGE_WIDTH_PT = 1008;
const PAGE_HEIGHT_PT = 612;
const MARGIN_PT = 36;

const BANANA_IMG_SRC = '/banana-boy.png';
const BANANA_UNFILLED_OPACITY = 0.22;
// Render canvases at 3× the PDF-point dimensions so the embedded PNG stays
// crisp on print. The banana strip is rendered at a FIXED height regardless
// of the cell's actual row height — otherwise tile width (vertical-fit) drifts
// per row and the banana count varies between rows. The image is drawn into
// the cell vertically centered.
const BANANA_DPI_SCALE = 3;
const BANANA_DRAW_HEIGHT_PT = 10;

// Cap wrapped text at this many lines per cell; further wrapping is replaced
// with an ellipsis on the last kept line. Two lines balances density vs.
// keeping the description readable.
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

// Hard character cap applied before autoTable wraps. Truncated values get a
// trailing ellipsis (…). The MAX_LINES_PER_CELL wrap cap still applies on top.
const PRINT_CHAR_LIMITS = {
    'Job': 25,
    'Description': 25,
};

const HEADER_LABELS = {
    'Release #': 'rel. #',
    'Job Comp': 'Install Prog',
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

// Rasterize the tiled banana progress bar to a dataURL PNG at the actual
// cell aspect ratio. Mirrors BananaIcon: repeat-x at vertical-fit, low-alpha
// base layer + full-alpha clipped foreground covering `progress * width`.
function buildBananaPng(bananaImg, progress, canvasW, canvasH) {
    const canvas = document.createElement('canvas');
    canvas.width = canvasW;
    canvas.height = canvasH;
    const ctx = canvas.getContext('2d');
    ctx.imageSmoothingEnabled = false;

    const tileH = canvasH;
    const tileW = bananaImg.width * (tileH / bananaImg.height);
    if (tileW <= 0) return canvas.toDataURL('image/png');
    const tilesNeeded = Math.ceil(canvasW / tileW);

    ctx.globalAlpha = BANANA_UNFILLED_OPACITY;
    for (let i = 0; i < tilesNeeded; i++) {
        ctx.drawImage(bananaImg, i * tileW, 0, tileW, tileH);
    }

    const fillW = Math.max(0, Math.min(1, progress)) * canvasW;
    if (fillW > 0) {
        ctx.save();
        ctx.beginPath();
        ctx.rect(0, 0, fillW, canvasH);
        ctx.clip();
        ctx.globalAlpha = 1;
        for (let i = 0; i < tilesNeeded; i++) {
            ctx.drawImage(bananaImg, i * tileW, 0, tileW, tileH);
        }
        ctx.restore();
    }

    return canvas.toDataURL('image/png');
}

// Returns a getter that lazily produces a per-(progress, w) banana PNG at a
// FIXED draw height. Within the Urgency column the cell width is constant, so
// this collapses to one PNG per unique progress value.
function makeBananaProvider(bananaImg) {
    const cache = new Map();
    const hPx = Math.max(2, Math.round(BANANA_DRAW_HEIGHT_PT * BANANA_DPI_SCALE));
    return (progress, drawWPt) => {
        const wPx = Math.max(2, Math.round(drawWPt * BANANA_DPI_SCALE));
        const key = `${progress}|${wPx}`;
        let png = cache.get(key);
        if (!png) {
            png = buildBananaPng(bananaImg, progress, wPx, hPx);
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
    const text = String(value || '—');
    const limit = PRINT_CHAR_LIMITS[column];
    if (limit && text.length > limit) {
        return text.slice(0, limit - 1).trimEnd() + '…';
    }
    return text;
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
            progress: getBananaProgress(job['Stage'] || 'Released'),
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

    const bananaImg = await loadImage(BANANA_IMG_SRC);
    const bananaProvider = makeBananaProvider(bananaImg);
    const pmGroups = groupByPm(jobs);
    const columnStyles = buildColumnStyles(columnHeaders, columnWidthPercent);
    const head = [columnHeaders.map((col) => HEADER_LABELS[col] ?? col)];

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
            styles: {
                font: 'helvetica',
                fontSize: 7,
                cellPadding: { top: 0.75, bottom: 0.75, left: 3, right: 3 },
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
                fontSize: 7.5,
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
                const drawH = Math.min(BANANA_DRAW_HEIGHT_PT, data.cell.height - 2);
                if (drawW <= 0 || drawH <= 0) return;
                const png = bananaProvider(rowMeta.progress, drawW);
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
