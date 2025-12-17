/**
 * Shared formatting utilities for displaying data
 */

/**
 * Format a date value for display
 */
export function formatDate(dateValue) {
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
export function formatCellValue(value) {
    if (value === null || value === undefined || value === '') {
        return '—';
    }
    if (Array.isArray(value)) {
        return value.join(', ');
    }
    return value;
}

