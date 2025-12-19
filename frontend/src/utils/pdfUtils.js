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

    // Find the index of the Type column
    const typeColumnIndex = columns.findIndex(col => col === 'Type' || col.toLowerCase() === 'type');

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
        columnStyles: {
            // Explicit column widths for all columns
            0: { cellWidth: 50, halign: 'center' }, // Order Number
            1: { cellWidth: 100, halign: 'center' }, // Submittals Id
            2: { cellWidth: 70, halign: 'center' }, // Project Number
            3: { cellWidth: 210, halign: 'center' }, // Project Name
            4: { cellWidth: 210, halign: 'center' }, // Title
            5: { cellWidth: 90, halign: 'center' }, // Ball In Court
            6: { cellWidth: 80, halign: 'center' }, // Type
            7: { cellWidth: 80, halign: 'center' }, // Status
            8: { cellWidth: 110, halign: 'center' }, // Submittal Manager
            9: { cellWidth: 200, halign: 'center' }, // Notes
        },
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

