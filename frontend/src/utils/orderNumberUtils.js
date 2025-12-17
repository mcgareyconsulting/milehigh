import { getBallInCourt, parseOrderNumber } from './rowDataAccessors';

/**
 * Calculate a new "top bump" order number when moving a row above the current #1
 * for a given ball_in_court group.
 *
 * Rules:
 * - If the smallest order >= 1, use 0.5
 * - If there are already decimals < 1, keep halving the current smallest positive order
 */
export function calculateTopOrderNumber(draggedRow, allRows) {
    const draggedBallInCourt = getBallInCourt(draggedRow);

    // Filter rows to only those with the same ball_in_court (use all rows, not just filtered)
    const sameBallInCourtRows = allRows.filter(row => {
        return String(getBallInCourt(row)) === String(draggedBallInCourt);
    });

    if (sameBallInCourtRows.length === 0) {
        return 0.5;
    }

    // Sort by current order number
    const sortedRows = [...sameBallInCourtRows].sort((a, b) => {
        const orderA = parseOrderNumber(a);
        const orderB = parseOrderNumber(b);
        return orderA - orderB;
    });

    const first = sortedRows[0];
    const firstOrder = parseOrderNumber(first, 1);

    // If the first order is an integer >= 1, just use 0.5
    if (firstOrder >= 1) {
        return 0.5;
    }

    // Otherwise, find the smallest positive order and halve it
    let minPositive = Infinity;
    for (const row of sortedRows) {
        const val = parseOrderNumber(row);
        if (!isNaN(val) && val > 0 && val < minPositive) {
            minPositive = val;
        }
    }

    const base = minPositive === Infinity ? 1 : minPositive;
    const newOrder = base / 2;

    // Round to reasonable precision (4 decimal places)
    return Math.round(newOrder * 10000) / 10000;
}

/**
 * Parse order number with support for decimal urgent orders
 */
export function parseOrderNumberWithUrgent(row) {
    const raw = row.order_number ?? row['Order Number'] ?? null;
    if (raw === null || raw === undefined) return null;

    const parsed = typeof raw === 'number' ? raw : parseFloat(raw);
    return isNaN(parsed) ? null : parsed;
}

