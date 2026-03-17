import { useState, useCallback } from 'react';
import { draftingWorkLoadApi } from '../services/draftingWorkLoadApi';

/**
 * Determine zone of a submittal based on order_number.
 * 'ordered' (>= 1), 'urgent' (0 < x < 1), or 'unordered' (null)
 */
function getSubmittalZone(row) {
    const order = parseFloat(row['ORDER #'] ?? row.order_number ?? 'NaN');
    if (Number.isNaN(order)) return 'unordered';
    if (order >= 1) return 'ordered';
    if (order > 0 && order < 1) return 'urgent';
    return 'unordered';
}

/**
 * Get the BIC string for a row.
 */
function getBic(row) {
    return String(row.ball_in_court ?? row['BIC'] ?? '');
}

/**
 * Get the order number for a row as a float, or NaN.
 */
function getOrder(row) {
    return parseFloat(row['ORDER #'] ?? row.order_number ?? 'NaN');
}

/**
 * Get the submittal ID for a row.
 */
function getId(row) {
    return row['Submittals Id'] ?? row.submittal_id;
}

/**
 * Find the minimum ordered (>= 1) order number in a BIC group.
 * Returns Infinity if no ordered rows exist.
 */
function minOrderedInGroup(allRows, bic) {
    let min = Infinity;
    for (const r of allRows) {
        if (getBic(r) !== bic) continue;
        const o = getOrder(r);
        if (!Number.isNaN(o) && o >= 1 && o < min) min = o;
    }
    return min;
}

/**
 * Custom hook for managing drag and drop in DWL table.
 *
 * @param {Array} allRows - All rows (unfiltered submittals)
 * @param {Function} refetch - Re-fetch data after a successful drop
 * @param {boolean} isAdmin - Whether current user is admin
 */
export function useDWLDragAndDrop(allRows, refetch, isAdmin) {
    const [draggedRow, setDraggedRow] = useState(null);
    const [dragOverSubmittalId, setDragOverSubmittalId] = useState(null);
    const [dragOverHalf, setDragOverHalf] = useState(null); // 'top' | 'bottom'

    // ---- helpers to clear state ----
    const clearDrag = useCallback(() => {
        setDraggedRow(null);
        setDragOverSubmittalId(null);
        setDragOverHalf(null);
    }, []);

    // ---- handlers ----

    const handleDragStart = useCallback((e, row) => {
        const bic = getBic(row);
        if (!isAdmin || bic.includes(',')) {
            e.preventDefault();
            return;
        }
        setDraggedRow(row);
    }, [isAdmin]);

    const handleDragOver = useCallback((e, targetRow) => {
        e.preventDefault();
        if (!draggedRow) { setDragOverSubmittalId(null); return; }

        // Cross-BIC or multi-assignee target → reject
        const draggedBic = getBic(draggedRow);
        const targetBic = getBic(targetRow);
        if (draggedBic !== targetBic || targetBic.includes(',')) {
            setDragOverSubmittalId(null);
            return;
        }

        // Determine top/bottom half
        const rect = e.currentTarget.getBoundingClientRect();
        const half = (e.clientY - rect.top) < (rect.height / 2) ? 'top' : 'bottom';

        setDragOverSubmittalId(getId(targetRow));
        setDragOverHalf(half);
    }, [draggedRow]);

    const handleDragLeave = useCallback((e) => {
        if (!e.currentTarget.contains(e.relatedTarget)) {
            setDragOverSubmittalId(null);
            setDragOverHalf(null);
        }
    }, []);

    const handleDragEnd = useCallback(() => { clearDrag(); }, [clearDrag]);

    const handleDrop = useCallback(async (e, targetRow, rowsForLookup) => {
        e.preventDefault();
        if (!draggedRow) { clearDrag(); return; }

        try {
            const draggedId = getId(draggedRow);
            const bic = getBic(targetRow);

            // --- resolve zone and target_order ---
            let targetZone = getSubmittalZone(targetRow);
            let targetOrder = null;
            let isNoOp = false;

            const draggedZone = getSubmittalZone(draggedRow);
            const draggedOrder = getOrder(draggedRow);

            if (targetZone === 'ordered') {
                const targetOrderNum = getOrder(targetRow);

                // "drop target above submittal 1" → urgency at 0.9
                if (dragOverHalf === 'top') {
                    const lowestOrdered = minOrderedInGroup(rowsForLookup, bic);
                    if (targetOrderNum <= lowestOrdered) {
                        // Dropping above the first ordered item → urgency
                        targetZone = 'urgent';
                        targetOrder = null;
                    } else {
                        targetOrder = targetOrderNum;
                    }
                } else {
                    // Bottom half: insert after this row = before the next ordered row
                    let nextOrder = null;
                    for (const r of rowsForLookup) {
                        if (getBic(r) !== bic) continue;
                        const o = getOrder(r);
                        if (Number.isNaN(o) || o < 1) continue;
                        if (o > targetOrderNum && (nextOrder === null || o < nextOrder)) {
                            nextOrder = o;
                        }
                    }
                    targetOrder = nextOrder; // null means append to end
                }

                // No-op checks (only relevant if we're still in ordered zone)
                if (targetZone === 'ordered' && draggedZone === 'ordered' && !Number.isNaN(draggedOrder)) {
                    if (targetOrder !== null && draggedOrder === targetOrder) {
                        // Dropping exactly where it already is
                        isNoOp = true;
                    } else if (targetOrder !== null) {
                        // Check: is the dragged row already the one right before targetOrder?
                        // E.g., dragged=5, targetOrder=6 → no move needed
                        let closestBelow = null;
                        for (const r of rowsForLookup) {
                            if (getBic(r) !== bic) continue;
                            const o = getOrder(r);
                            if (Number.isNaN(o) || o < 1 || o >= targetOrder) continue;
                            if (closestBelow === null || o > closestBelow) closestBelow = o;
                        }
                        if (closestBelow !== null && closestBelow === draggedOrder) {
                            isNoOp = true;
                        }
                    } else if (targetOrder === null) {
                        // Appending to end — no-op if dragged is already the last ordered
                        let maxOrdered = 0;
                        for (const r of rowsForLookup) {
                            if (getBic(r) !== bic) continue;
                            const o = getOrder(r);
                            if (!Number.isNaN(o) && o >= 1 && o > maxOrdered) maxOrdered = o;
                        }
                        if (draggedOrder >= maxOrdered) isNoOp = true;
                    }
                }
            }

            // Urgency zone — handle within-urgent reorder or no-op
            if (targetZone === 'urgent' && draggedZone === 'urgent') {
                const targetId = getId(targetRow);
                if (draggedId === targetId) {
                    isNoOp = true;
                } else {
                    const urgentItems = rowsForLookup
                        .filter(r => getBic(r) === bic && getSubmittalZone(r) === 'urgent')
                        .sort((a, b) => getOrder(a) - getOrder(b));
                    const draggedIdx = urgentItems.findIndex(r => getId(r) === draggedId);
                    const targetIdx  = urgentItems.findIndex(r => getId(r) === targetId);
                    const insertBefore = dragOverHalf === 'top';
                    if (insertBefore  && draggedIdx + 1 === targetIdx) isNoOp = true;
                    if (!insertBefore && draggedIdx - 1 === targetIdx) isNoOp = true;
                    if (!isNoOp) {
                        targetOrder = getOrder(targetRow);
                        await draftingWorkLoadApi.dragReorder(draggedId, 'urgent', targetOrder, insertBefore);
                        await refetch();
                        return;
                    }
                }
            }

            // Unordered zone — no-op if already unordered
            if (targetZone === 'unordered' && draggedZone === 'unordered') {
                isNoOp = true;
            }

            if (isNoOp) { clearDrag(); return; }

            await draftingWorkLoadApi.dragReorder(draggedId, targetZone, targetOrder);
            await refetch();
        } catch (error) {
            console.error('Drag reorder failed:', error);
        } finally {
            clearDrag();
        }
    }, [draggedRow, dragOverHalf, refetch, clearDrag]);

    return {
        draggedRow,
        dragOverSubmittalId,
        dragOverHalf,
        handleDragStart,
        handleDragOver,
        handleDragLeave,
        handleDragEnd,
        handleDrop,
    };
}
