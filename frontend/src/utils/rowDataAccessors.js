/**
 * Utility functions for accessing row data with fallback field names
 */

/**
 * Get ball in court value from a row
 */
export function getBallInCourt(row) {
    return row.ball_in_court ?? row['Ball In Court'] ?? '';
}

/**
 * Get row ID from a row
 */
export function getRowId(row) {
    return row['Submittals Id'] || row.submittal_id;
}

/**
 * Get order number from a row
 */
export function getOrderNumber(row) {
    return row.order_number ?? row['Order Number'] ?? null;
}

/**
 * Parse order number as a number, with fallback
 */
export function parseOrderNumber(row, fallback = 999999) {
    const raw = getOrderNumber(row);
    if (raw === null || raw === undefined) return fallback;
    return typeof raw === 'number' ? raw : parseFloat(raw) || fallback;
}

