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
            }
        }
    }, [draggedRow, displayRows]);

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
            // Case 2: reordering in the middle or end -> renumber entire group to 1, 2, 3, ...

            // Remove dragged row from group
            const groupWithoutDragged = sortedGroup.filter(r => getRowId(r) !== draggedRowId);

            // Find target index in the reduced group
            const targetIndexInReduced = groupWithoutDragged.findIndex(r => getRowId(r) === targetRowId);

            if (targetIndexInReduced === -1) {
                setDraggedIndex(null);
                setDragOverIndex(null);
                setDraggedRow(null);
                return;
            }

            // Determine insert position: if dragging down, insert after target; if up, before target
            let insertPosition;
            if (draggedPosition < targetPosition) {
                insertPosition = targetIndexInReduced + 1;
            } else {
                insertPosition = targetIndexInReduced;
            }

            const clampedInsert = Math.max(0, Math.min(insertPosition, groupWithoutDragged.length));

            const reorderedGroup = [
                ...groupWithoutDragged.slice(0, clampedInsert),
                draggedRow,
                ...groupWithoutDragged.slice(clampedInsert),
            ];

            // Renumber group while preserving meaning of decimal "urgent" orders:
            // - A contiguous prefix of rows whose current order < 1 keep their decimal values
            // - Everything after that prefix is renumbered to 1, 2, 3, ... based on new order
            let urgentPrefixLength = 0;

            for (let i = 0; i < reorderedGroup.length; i++) {
                const row = reorderedGroup[i];
                const currentOrderRaw = row.order_number ?? row['Order Number'] ?? null;
                const currentOrder = typeof currentOrderRaw === 'number'
                    ? currentOrderRaw
                    : currentOrderRaw !== null && currentOrderRaw !== undefined
                        ? parseFloat(currentOrderRaw)
                        : null;

                if (currentOrder !== null && !isNaN(currentOrder) && currentOrder > 0 && currentOrder < 1) {
                    urgentPrefixLength += 1;
                } else {
                    break;
                }
            }

            let nextIntegerOrder = 1;

            for (let i = 0; i < reorderedGroup.length; i++) {
                const row = reorderedGroup[i];
                const rowId = getRowId(row);
                const currentOrderRaw = row.order_number ?? row['Order Number'] ?? null;
                const currentOrder = typeof currentOrderRaw === 'number'
                    ? currentOrderRaw
                    : currentOrderRaw !== null && currentOrderRaw !== undefined
                        ? parseFloat(currentOrderRaw)
                        : null;

                let newOrderNumber;

                if (i < urgentPrefixLength && currentOrder !== null && !isNaN(currentOrder) && currentOrder > 0 && currentOrder < 1) {
                    // Preserve existing urgent decimal orders at the top
                    newOrderNumber = currentOrder;
                } else {
                    // Renumber everything after the urgent prefix as 1, 2, 3, ...
                    newOrderNumber = nextIntegerOrder;
                    nextIntegerOrder += 1;
                }

                // Only send update if the order actually changed
                if (rowId && currentOrder !== newOrderNumber) {
                    // eslint-disable-next-line no-await-in-loop
                    await updateOrderNumber(rowId, newOrderNumber);
                }
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
        handleDrop,
    };
}

