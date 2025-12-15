import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';

/**
 * Format a date value for display
 */
function formatDate(dateValue) {
    if (!dateValue) return '—';
    try {
        const date = new Date(dateValue);
        if (isNaN(date.getTime())) return '—';
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        const year = date.getFullYear();
        return `${month}/${day}/${year}`;
    } catch (e) {
        return '—';
    }
}

/**
 * Format a cell value for display
 */
function formatCellValue(value) {
    if (value === null || value === undefined || value === '') {
        return '—';
    }
    if (Array.isArray(value)) {
        return value.join(', ');
    }
    return value;
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
 */
function prepareTableData(rows, columns) {
    return rows.map(row => {
        return columns.map(column => {
            let value = getColumnValue(row, column);

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

    // Prepare table data
    const tableData = prepareTableData(displayRows, columns);

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
    });

    // Save the PDF
    const fileName = `Drafting_Work_Load_${new Date().toISOString().split('T')[0]}.pdf`;
    doc.save(fileName);
}

