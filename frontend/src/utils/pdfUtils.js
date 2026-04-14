/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Generates a formatted 11x17 landscape PDF of the Drafting Work Load table with DRR-row highlighting.
 * exports:
 *   generateDraftingWorkLoadPDF: Builds and downloads a PDF from filtered/sorted DWL rows and columns
 * imports_from: [jspdf, jspdf-autotable, ./formatters]
 * imported_by: [pages/DraftingWorkLoad.jsx]
 * invariants:
 *   - DRR highlight (green) is applied only to the TYPE column cell, not the entire row
 *   - Column widths array must stay in sync with DESIRED_COLUMN_ORDER from columns.js
 * updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
 */
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
 * Prepare table data for PDF export
 * Returns both the table data and a set of row indices that are DRR rows
 */
function prepareTableData(rows, columns) {
    const drrRowIndices = new Set();

    const tableData = rows.map((row, rowIndex) => {
        // Check if this row is a DRR row
        const rowType = row.type ?? row['TYPE'] ?? '';
        if (rowType === 'Drafting Release Review') {
            drrRowIndices.add(rowIndex);
        }

        return columns.map(column => {
            let value = getColumnValue(row, column);

            // Apply type mapping for TYPE column
            if (column === 'TYPE') {
                value = formatTypeValue(value);
            }

            // Format dates (DUE DATE); LIFESPAN is a number, not a date
            if (column === 'DUE DATE' || (column.includes('Date') && column !== 'LIFESPAN')) {
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
        format: [1224, 792] // 11x17 inches in points (17" x 11" landscape)
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

    // Find the index of the TYPE column (for DRR green highlight)
    const typeColumnIndex = columns.findIndex(col => col === 'TYPE');

    // Build column styles by index (ORDER #, PROJ. #, NAME, TITLE, PROCORE STATUS, BIC, LAST BIC, TYPE, COMP. STATUS, SUB MANAGER, DUE DATE, LIFESPAN, NOTES)
    const defaultWidth = 80;
    const columnStyles = columns.reduce((acc, _, i) => {
        const widths = [50, 65, 180, 180, 80, 100, 70, 70, 90, 100, 75, 50, 200]; // match new column order
        acc[i] = { cellWidth: widths[i] ?? defaultWidth, halign: 'center' };
        return acc;
    }, {});

    // Generate table
    autoTable(doc, {
        head: [columns],
        body: tableData,
        startY: 65,
        styles: {
            fontSize: 10,
            cellPadding: 2,
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
        columnStyles,
        margin: { top: 65, left: 10, right: 10 },
        didParseCell: function (data) {
            // Highlight only the Type column cell for DRR rows with green background
            // data.row.index is 0-based for body rows (header is -1)
            // data.column.index is the column index
            if (data.row.index >= 0 &&
                drrRowIndices.has(data.row.index) &&
                typeColumnIndex !== -1 &&
                data.column.index === typeColumnIndex) {
                data.cell.styles.fillColor = [220, 252, 231]; // Light green (equivalent to bg-green-100)
            }
        },
    });

    // Save the PDF
    const fileName = `Drafting_Work_Load_${new Date().toISOString().split('T')[0]}.pdf`;
    doc.save(fileName);
}

