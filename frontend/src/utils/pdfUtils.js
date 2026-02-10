import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';
import { formatDate, formatCellValue } from './formatters';

/**
 * Format type value using the same mapping as the UI
 */
function formatTypeValue(value) {
    if (value === null || value === undefined || value === '') {
        return value;
    }
    const typeMap = {
        'Submittal For Gc  Approval': 'Sub GC',
        'Submittal for GC  Approval': 'Sub GC',
        'Drafting Release Review': 'DRR',
    };
    return typeMap[value] || value;
}

/**
 * Get column value from row, trying multiple field name formats
 */
function getColumnValue(row, column) {
    // Try exact column name first
    if (row[column] !== undefined && row[column] !== null) {
        return row[column];
    }
    // Try snake_case version
    const snakeCase = column.toLowerCase().replace(/\s+/g, '_');
    if (row[snakeCase] !== undefined && row[snakeCase] !== null) {
        return row[snakeCase];
    }
    // Try camelCase version
    const camelCase = column.replace(/\s+(.)/g, (_, c) => c.toUpperCase()).replace(/^./, c => c.toLowerCase());
    if (row[camelCase] !== undefined && row[camelCase] !== null) {
        return row[camelCase];
    }
    return '';
}

/**
 * Column display names that hold raw date values (to format for PDF)
 */
const DATE_COLUMNS = new Set(['Due Date']);

/**
 * Prepare table data for PDF export
 * Returns both the table data and a set of row indices that are DRR rows
 */
function prepareTableData(rows, columns) {
    const drrRowIndices = new Set();

    const tableData = rows.map((row, rowIndex) => {
        // Check if this row is a DRR row
        const rowType = row.type ?? row['Type'] ?? '';
        if (rowType === 'Drafting Release Review') {
            drrRowIndices.add(rowIndex);
        }

        return columns.map(column => {
            let value = getColumnValue(row, column);

            // Apply type mapping for Type column
            if (column === 'Type') {
                value = formatTypeValue(value);
            }

            // Format only columns that store raw dates (e.g. Due Date). Lifespan / Last BIC Update are already "X days"
            if (DATE_COLUMNS.has(column)) {
                value = formatDate(value);
            } else {
                value = formatCellValue(value);
            }

            // Truncate long values for PDF
            if (typeof value === 'string' && value.length > 50) {
                value = value.substring(0, 47) + '...';
            }

            return value;
        });
    });

    return { tableData, drrRowIndices };
}

// 11x17 landscape: 17" = 1224pt. Use 10pt side margins → table width 1204pt
const PAGE_WIDTH_PT = 1224;
const SIDE_MARGIN_PT = 10;
const AVAILABLE_TABLE_WIDTH_PT = PAGE_WIDTH_PT - 2 * SIDE_MARGIN_PT;

/**
 * Relative column widths (weights) per column name. We scale these so the table fills the page.
 */
const COLUMN_WIDTHS = {
    'Order Number': 40,
    'Submittals Id': 80,
    'Project Number': 55,
    'Project Name': 140,
    'Title': 140,
    'Ball In Court': 70,
    'Last BIC Update': 60,
    'Type': 60,
    'Status': 60,
    'Procore Status': 70,
    'Submittal Manager': 90,
    'Lifespan': 55,
    'Due Date': 60,
    'Notes': 174,
};

const DEFAULT_COLUMN_WIDTH = 86;

/**
 * Build columnStyles so the table always fills the available width (1204pt).
 * Scales preferred widths proportionally and assigns any rounding remainder to the last column.
 */
function buildColumnStyles(columns) {
    const preferred = columns.map(col => COLUMN_WIDTHS[col] ?? DEFAULT_COLUMN_WIDTH);
    const sum = preferred.reduce((a, b) => a + b, 0);
    const scale = sum > 0 ? AVAILABLE_TABLE_WIDTH_PT / sum : 1;
    const widths = preferred.map((w, i) => Math.round(w * scale));
    // Fix rounding: ensure total is exactly AVAILABLE_TABLE_WIDTH_PT (give remainder to last column)
    const total = widths.reduce((a, b) => a + b, 0);
    const diff = AVAILABLE_TABLE_WIDTH_PT - total;
    if (diff !== 0 && widths.length > 0) {
        widths[widths.length - 1] += diff;
    }
    const styles = {};
    columns.forEach((col, i) => {
        styles[i] = {
            cellWidth: widths[i],
            halign: 'center',
        };
    });
    return styles;
}

/**
 * Generate and download a PDF of the drafting work load
 * @param {Array} displayRows - The filtered/sorted rows to export
 * @param {Array} columns - The column headers
 * @param {Date|null} lastUpdated - The last update timestamp
 */
export function generateDraftingWorkLoadPDF(displayRows, columns, lastUpdated = null) {
    if (displayRows.length === 0) {
        alert('No data to export');
        return;
    }

    // Use 11x17 paper size (17" x 11" in landscape = 1224pt x 792pt)
    const doc = new jsPDF({
        orientation: 'landscape',
        unit: 'pt',
        format: [PAGE_WIDTH_PT, 792] // 11x17 inches in points (17" x 11" landscape)
    });

    // Add title
    doc.setFontSize(18);
    doc.text('Drafting Work Load', 10, 20);

    // Add metadata
    doc.setFontSize(10);
    const formattedDate = lastUpdated ? new Date(lastUpdated).toLocaleString() : 'Unknown';
    doc.text(`Generated: ${new Date().toLocaleString()}`, 10, 35);
    doc.text(`Last Updated: ${formattedDate}`, 10, 47);
    doc.text(`Total Records: ${displayRows.length}`, 10, 59);

    // Prepare table data and get DRR row indices
    const { tableData, drrRowIndices } = prepareTableData(displayRows, columns);

    // Find the index of the Type column
    const typeColumnIndex = columns.findIndex(col => col === 'Type' || col.toLowerCase() === 'type');

    // Generate table — full width between side margins (1204pt)
    autoTable(doc, {
        head: [columns],
        body: tableData,
        startY: 65,
        tableWidth: AVAILABLE_TABLE_WIDTH_PT,
        margin: { left: SIDE_MARGIN_PT, right: SIDE_MARGIN_PT },
        styles: {
            fontSize: 10,
            cellPadding: 3,
            halign: 'center',
        },
        headStyles: {
            fillColor: [100, 100, 100],
            textColor: [255, 255, 255],
            fontStyle: 'bold',
            halign: 'center',
        },
        alternateRowStyles: {
            fillColor: [220, 220, 220],
        },
        columnStyles: buildColumnStyles(columns),
        didParseCell: function (data) {
            // Highlight only body cells in the Type column for DRR rows (never the column header)
            const isBody = (data.section || data.row?.section) === 'body';
            const isTypeColumn = typeColumnIndex !== -1 && data.column.index === typeColumnIndex;
            const isDRRRow = data.row.index >= 0 && drrRowIndices.has(data.row.index);
            if (isBody && isTypeColumn && isDRRRow) {
                data.cell.styles.fillColor = [220, 252, 231]; // Light green (equivalent to bg-green-100)
            }
        },
    });

    // Save the PDF
    const fileName = `Drafting_Work_Load_${new Date().toISOString().split('T')[0]}.pdf`;
    doc.save(fileName);
}

