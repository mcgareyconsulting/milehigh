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

            // Format dates
            if (column.includes('Date') || column.includes('date')) {
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

    const doc = new jsPDF('landscape', 'pt', 'letter');

    // Add title
    doc.setFontSize(18);
    doc.text('Drafting Work Load', 40, 30);

    // Add metadata
    doc.setFontSize(10);
    const formattedDate = lastUpdated ? new Date(lastUpdated).toLocaleString() : 'Unknown';
    doc.text(`Generated: ${new Date().toLocaleString()}`, 40, 50);
    doc.text(`Last Updated: ${formattedDate}`, 40, 65);
    doc.text(`Total Records: ${displayRows.length}`, 40, 80);

    // Prepare table data and get DRR row indices
    const { tableData, drrRowIndices } = prepareTableData(displayRows, columns);

    // Generate table
    autoTable(doc, {
        head: [columns],
        body: tableData,
        startY: 90,
        styles: {
            fontSize: 7,
            cellPadding: 2,
        },
        headStyles: {
            fillColor: [100, 100, 100],
            textColor: [255, 255, 255],
            fontStyle: 'bold',
        },
        alternateRowStyles: {
            fillColor: [245, 245, 245],
        },
        columnStyles: {
            // Make certain columns narrower
            0: { cellWidth: 40 }, // Order Number
            1: { cellWidth: 60 }, // Submittals Id
            5: { cellWidth: 80 }, // Ball In Court
            9: { cellWidth: 120 }, // Notes
        },
        margin: { top: 90, left: 40, right: 40 },
        didParseCell: function (data) {
            // Highlight DRR rows with green background
            // data.row.index is 0-based for body rows (header is -1)
            if (data.row.index >= 0 && drrRowIndices.has(data.row.index)) {
                data.cell.styles.fillColor = [220, 252, 231]; // Light green (equivalent to bg-green-100)
            }
        },
    });

    // Save the PDF
    const fileName = `Drafting_Work_Load_${new Date().toISOString().split('T')[0]}.pdf`;
    doc.save(fileName);
}

