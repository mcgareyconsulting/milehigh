/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Provides safe accessors for submittal row fields that may appear under different key names (snake_case vs display-name).
 * exports:
 *   getBallInCourt: Returns ball_in_court from a row with fallback keys
 *   getRowId: Returns the submittal ID from a row
 *   getOrderNumber: Returns raw order number from a row
 *   parseOrderNumber: Parses order number as a float with a fallback default
 * imports_from: []
 * imported_by: [utils/orderNumberUtils.js]
 * invariants:
 *   - All accessors use nullish coalescing; callers should not assume a non-null return
 * updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
 */

/**
 * Utility functions for accessing row data with fallback field names
 */

/**
 * Get ball in court value from a row
 */
export function getBallInCourt(row) {
    return row.ball_in_court ?? row['BIC'] ?? row['Ball In Court'] ?? '';
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
    return row.order_number ?? row['ORDER #'] ?? row['Order Number'] ?? null;
}

/**
 * Parse order number as a number, with fallback
 */
export function parseOrderNumber(row, fallback = 999999) {
    const raw = getOrderNumber(row);
    if (raw === null || raw === undefined) return fallback;
    return typeof raw === 'number' ? raw : parseFloat(raw) || fallback;
}

