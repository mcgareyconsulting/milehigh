/**
 * Shared formatting utilities for displaying data
 */

/**
 * Format a date value for display
 * Parses dates without timezone conversion to avoid day shift issues
 */
export function formatDate(dateValue) {
    if (!dateValue) return '—';
    try {
        // If it's already in mm/dd/yyyy format, return as is
        if (typeof dateValue === 'string' && /^\d{2}\/\d{2}\/\d{4}$/.test(dateValue)) {
            return dateValue;
        }
        // If it's in YYYY-MM-DD format, parse directly without timezone conversion
        if (typeof dateValue === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(dateValue)) {
            const [year, month, day] = dateValue.split('-');
            return `${month}/${day}/${year}`;
        }
        // For other formats, try to parse as Date but use UTC methods to avoid timezone shift
        const date = new Date(dateValue);
        if (isNaN(date.getTime())) return '—';
        // Use UTC methods to avoid timezone conversion
        const month = String(date.getUTCMonth() + 1).padStart(2, '0');
        const day = String(date.getUTCDate()).padStart(2, '0');
        const year = date.getUTCFullYear();
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

/**
 * Format a date value for short display (M/D/YY)
 * Parses dates without timezone conversion to avoid day shift issues
 */
export function formatDateShort(dateValue) {
    if (!dateValue) return '—';
    try {
        if (typeof dateValue === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(dateValue)) {
            const [year, month, day] = dateValue.split('-');
            return `${parseInt(month)}/${parseInt(day)}/${year.slice(2)}`;
        }
        if (typeof dateValue === 'string' && /^\d{2}\/\d{2}\/\d{4}$/.test(dateValue)) {
            const [month, day, year] = dateValue.split('/');
            return `${parseInt(month)}/${parseInt(day)}/${year.slice(2)}`;
        }
        const date = new Date(dateValue);
        if (isNaN(date.getTime())) return '—';
        const month = date.getUTCMonth() + 1;
        const day = date.getUTCDate();
        const year = String(date.getUTCFullYear()).slice(2);
        return `${month}/${day}/${year}`;
    } catch (e) {
        return '—';
    }
}

/**
 * Calculate and format days since a date/time
 * Returns the number of days as a string (e.g., "0 days", "1 day", "5 days")
 */
export function formatDaysAgo(dateValue) {
    if (!dateValue) return '—';
    
    try {
        const date = new Date(dateValue);
        if (isNaN(date.getTime())) return '—';
        
        const now = new Date();
        const diffTime = now - date;
        const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));
        
        // Handle edge cases
        if (diffDays < 0) return '0 days'; // Future date, show as 0
        if (diffDays === 0) return '0 days';
        if (diffDays === 1) return '1 day';
        
        return `${diffDays} days`;
    } catch (e) {
        return '—';
    }
}

