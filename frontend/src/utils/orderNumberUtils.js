import { getBallInCourt, parseOrderNumber } from './rowDataAccessors';

/**
 * Calculate a new "top bump" order number when moving a row above the current #1
 * for a given ball_in_court group.
 *
 * Rules:
 * - If the smallest order >= 1, use 0.9 (least urgent urgency slot)
 * - If there are already urgency slots (0.1-0.9), find the highest available slot
 * - If all 9 slots are filled, use 1.0 (regular order)
 */
export function calculateTopOrderNumber(draggedRow, allRows) {
    const draggedBallInCourt = getBallInCourt(draggedRow);

    // Filter rows to only those with the same ball_in_court (use all rows, not just filtered)
    const sameBallInCourtRows = allRows.filter(row => {
        return String(getBallInCourt(row)) === String(draggedBallInCourt);
    });

    if (sameBallInCourtRows.length === 0) {
        return 0.9; // Use least urgent slot if no other rows
    }

    // Sort by current order number
    const sortedRows = [...sameBallInCourtRows].sort((a, b) => {
        const orderA = parseOrderNumber(a);
        const orderB = parseOrderNumber(b);
        return orderA - orderB;
    });

    const first = sortedRows[0];
    const firstOrder = parseOrderNumber(first, 1);

    // If the first order is >= 1, use 0.9 (least urgent slot)
    if (firstOrder >= 1) {
        return 0.9;
    }

    // Find all existing urgency slots (0.1-0.9)
    const validUrgencySlots = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9];
    const occupiedSlots = new Set();
    
    for (const row of sameBallInCourtRows) {
        const val = parseOrderNumber(row);
        if (!isNaN(val) && val > 0 && val < 1) {
            // Round to nearest tenth to match urgency slot
            const rounded = Math.round(val * 10) / 10;
            if (validUrgencySlots.includes(rounded)) {
                occupiedSlots.add(rounded);
            }
        }
    }

    // If all 9 slots are filled, return 1.0 (regular order)
    if (occupiedSlots.size >= 9) {
        return 1.0;
    }

    // Find the highest available slot (0.9 is least urgent, 0.1 is most urgent)
    // We want to use the least urgent available slot
    for (let i = validUrgencySlots.length - 1; i >= 0; i--) {
        if (!occupiedSlots.has(validUrgencySlots[i])) {
            return validUrgencySlots[i];
        }
    }

    // Fallback (shouldn't reach here)
    return 0.9;
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

