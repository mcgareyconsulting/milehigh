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
 * Parse a date string (YYYY-MM-DD) without timezone conversion
 * Returns {year, month, day} or null if invalid
 */
function parseDateOnly(dateString) {
    if (!dateString) return null;
    
    // If it's already a YYYY-MM-DD string, parse it directly
    if (typeof dateString === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(dateString)) {
        const [year, month, day] = dateString.split('-').map(Number);
        return { year, month, day };
    }
    
    // Otherwise, try to parse as ISO string and extract date components
    try {
        // If it's an ISO string with time, extract just the date part
        const dateStr = typeof dateString === 'string' ? dateString.split('T')[0] : dateString;
        if (/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
            const [year, month, day] = dateStr.split('-').map(Number);
            return { year, month, day };
        }
    } catch (e) {
        // Fall through to Date parsing
    }
    
    // Fallback to Date parsing (for other formats)
    try {
        const date = new Date(dateString);
        if (isNaN(date.getTime())) return null;
        return {
            year: date.getFullYear(),
            month: date.getMonth() + 1,
            day: date.getDate()
        };
    } catch (e) {
        return null;
    }
}

/**
 * Format a date value for display with 2-digit year (MM/DD/YY)
 */
export function formatDateShort(dateValue) {
    if (!dateValue) return '—';
    const parsed = parseDateOnly(dateValue);
    if (!parsed) return '—';
    const month = String(parsed.month).padStart(2, '0');
    const day = String(parsed.day).padStart(2, '0');
    const year = String(parsed.year).slice(-2); // Get last 2 digits of year
    return `${month}/${day}/${year}`;
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

