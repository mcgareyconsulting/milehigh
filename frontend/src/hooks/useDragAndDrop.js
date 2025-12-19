import { useState, useCallback } from 'react';
import { getBallInCourt, getRowId, parseOrderNumber } from '../utils/rowDataAccessors';
import { calculateTopOrderNumber } from '../utils/orderNumberUtils';

/**
 * Custom hook for managing drag and drop functionality in the drafting work load table
 */
export function useDragAndDrop(rows, displayRows, updateOrderNumber) {
    const [draggedIndex, setDraggedIndex] = useState(null);
    const [dragOverIndex, setDragOverIndex] = useState(null);
    const [draggedRow, setDraggedRow] = useState(null);

    const handleDragStart = useCallback((e, index, row) => {
        setDraggedIndex(index);
        setDraggedRow(row);
    }, []);

    const handleDragOver = useCallback((e, index) => {
        e.preventDefault();
        if (draggedRow) {
            const targetRow = displayRows[index];
            const draggedBallInCourt = getBallInCourt(draggedRow);
            const targetBallInCourt = getBallInCourt(targetRow);

            // Only allow drag over if same ball_in_court
            if (String(draggedBallInCourt) === String(targetBallInCourt)) {
                setDragOverIndex(index);
            } else {
                setDragOverIndex(null);
            }
        }
    }, [draggedRow, displayRows]);

    const handleDragLeave = useCallback((e) => {
        // Only clear if we're actually leaving the row (not just moving between child elements)
        if (!e.currentTarget.contains(e.relatedTarget)) {
            setDragOverIndex(null);
        }
    }, []);

    const handleDrop = useCallback(async (e, targetIndex, targetRow) => {
        e.preventDefault();

        if (!draggedRow) return;

        const draggedBallInCourt = getBallInCourt(draggedRow);
        const targetBallInCourt = getBallInCourt(targetRow);

        // Only allow drop if same ball_in_court
        if (String(draggedBallInCourt) !== String(targetBallInCourt)) {
            setDraggedIndex(null);
            setDragOverIndex(null);
            setDraggedRow(null);
            return;
        }

        // Work with all rows in this ball_in_court group, sorted by current order
        const draggedRowId = getRowId(draggedRow);
        const targetRowId = getRowId(targetRow);

        const sameBallInCourtRows = rows.filter(row => {
            return String(getBallInCourt(row)) === String(draggedBallInCourt);
        });

        const sortedGroup = [...sameBallInCourtRows].sort((a, b) => {
            const orderA = parseOrderNumber(a);
            const orderB = parseOrderNumber(b);
            return orderA - orderB;
        });

        const draggedPosition = sortedGroup.findIndex(r => getRowId(r) === draggedRowId);
        const targetPosition = sortedGroup.findIndex(r => getRowId(r) === targetRowId);

        if (draggedPosition === -1 || targetPosition === -1) {
            setDraggedIndex(null);
            setDragOverIndex(null);
            setDraggedRow(null);
            return;
        }

        const submittalId = draggedRowId;

        // Case 1: moving above the current first item -> use decimal bumping
        if (targetPosition === 0 && draggedPosition !== 0) {
            const newOrderNumber = calculateTopOrderNumber(draggedRow, rows);
            if (submittalId) {
                await updateOrderNumber(submittalId, newOrderNumber);
            }
        } else {
            // Case 2: reordering in the middle or end
            // Let the backend handle renumbering - just set the dragged row to the target position
            // The backend will handle renumbering all values >= 1 to be tight, while preserving
            // decimals < 1 and leaving NULL rows unchanged

            // Count urgent rows (decimals < 1) that come before the target
            let urgentCount = 0;
            for (let i = 0; i < targetPosition; i++) {
                const row = sortedGroup[i];
                const currentOrderRaw = row.order_number ?? row['Order Number'] ?? null;
                const currentOrder = typeof currentOrderRaw === 'number'
                    ? currentOrderRaw
                    : currentOrderRaw !== null && currentOrderRaw !== undefined
                        ? parseFloat(currentOrderRaw)
                        : null;

                if (currentOrder !== null && !isNaN(currentOrder) && currentOrder > 0 && currentOrder < 1) {
                    urgentCount += 1;
                } else {
                    break;
                }
            }

            // Count rows with order >= 1 that come before the target (excluding the dragged row)
            let regularCountBeforeTarget = 0;
            for (let i = 0; i < targetPosition; i++) {
                const row = sortedGroup[i];
                if (getRowId(row) === draggedRowId) {
                    continue; // Skip the dragged row
                }
                const currentOrderRaw = row.order_number ?? row['Order Number'] ?? null;
                const currentOrder = typeof currentOrderRaw === 'number'
                    ? currentOrderRaw
                    : currentOrderRaw !== null && currentOrderRaw !== undefined
                        ? parseFloat(currentOrderRaw)
                        : null;

                // Only count rows with order >= 1 (not NULL, not decimals < 1)
                if (currentOrder !== null && !isNaN(currentOrder) && currentOrder >= 1) {
                    regularCountBeforeTarget += 1;
                }
            }

            // Determine insert position: if dragging down, insert after target; if up, before target
            let insertOffset = 0;
            if (draggedPosition < targetPosition) {
                // Dragging down - check if target row has order >= 1
                const targetOrderRaw = targetRow.order_number ?? targetRow['Order Number'] ?? null;
                const targetOrder = typeof targetOrderRaw === 'number'
                    ? targetOrderRaw
                    : targetOrderRaw !== null && targetOrderRaw !== undefined
                        ? parseFloat(targetOrderRaw)
                        : null;

                // If target has order >= 1, insert after it; otherwise insert before
                if (targetOrder !== null && !isNaN(targetOrder) && targetOrder >= 1) {
                    insertOffset = 1;
                }
            }

            // Calculate target order number (1-based, after urgent decimals)
            const targetOrderNumber = regularCountBeforeTarget + insertOffset + 1;

            // Update the dragged row - backend will handle renumbering
            if (submittalId) {
                await updateOrderNumber(submittalId, targetOrderNumber);
            }
        }

        // Reset drag state
        setDraggedIndex(null);
        setDragOverIndex(null);
        setDraggedRow(null);
    }, [draggedRow, rows, updateOrderNumber]);

    return {
        draggedIndex,
        dragOverIndex,
        handleDragStart,
        handleDragOver,
        handleDragLeave,
        handleDrop,
    };
}

