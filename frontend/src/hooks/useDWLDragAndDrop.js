import { useState, useCallback } from 'react';
import { draftingWorkLoadApi } from '../services/draftingWorkLoadApi';

/**
 * Determine zone of a submittal based on order_number
 * @param {Object} row - Row with order_number or ORDER #
 * @returns {string} - 'ordered' (>= 1), 'urgent' (0 < x < 1), or 'unordered' (null)
 */
function getSubmittalZone(row) {
    const order = parseFloat(row['ORDER #'] ?? row.order_number ?? 'NaN');
    if (Number.isNaN(order)) return 'unordered';
    if (order >= 1) return 'ordered';
    if (order > 0 && order < 1) return 'urgent';
    return 'unordered';
}

/**
 * Custom hook for managing drag and drop in DWL table
 * @param {Array} allRows - All rows (unfiltered)
 * @param {Function} refetch - Function to refetch data after drag
 * @param {boolean} isAdmin - Whether current user is admin
 */
export function useDWLDragAndDrop(allRows, refetch, isAdmin) {
    const [draggedRow, setDraggedRow] = useState(null);
    const [dragOverSubmittalId, setDragOverSubmittalId] = useState(null);
    const [dragOverHalf, setDragOverHalf] = useState(null); // 'top' or 'bottom'

    const handleDragStart = useCallback((e, row) => {
        // Only allow if admin and not multi-assignee
        const ballInCourt = row.ball_in_court ?? row['BIC'] ?? '';
        const hasMultipleAssignees = String(ballInCourt).includes(',');

        if (!isAdmin || hasMultipleAssignees) {
            e.preventDefault();
            return;
        }

        setDraggedRow(row);
    }, [isAdmin]);

    const handleDragOver = useCallback((e, targetRow) => {
        e.preventDefault();

        if (!draggedRow) {
            setDragOverSubmittalId(null);
            return;
        }

        // Reject cross-BIC drops
        const draggedBic = draggedRow.ball_in_court ?? draggedRow['BIC'] ?? '';
        const targetBic = targetRow.ball_in_court ?? targetRow['BIC'] ?? '';
        if (String(draggedBic) !== String(targetBic)) {
            setDragOverSubmittalId(null);
            return;
        }

        // Reject multi-assignee targets
        const hasMultipleAssignees = String(targetBic).includes(',');
        if (hasMultipleAssignees) {
            setDragOverSubmittalId(null);
            return;
        }

        // Determine top/bottom half
        const rect = e.currentTarget.getBoundingClientRect();
        const midpoint = rect.height / 2;
        const offsetY = e.clientY - rect.top;
        const half = offsetY < midpoint ? 'top' : 'bottom';

        setDragOverSubmittalId(targetRow['Submittals Id'] ?? targetRow.submittal_id);
        setDragOverHalf(half);
    }, [draggedRow]);

    const handleDragLeave = useCallback((e) => {
        // Only clear when leaving the row (not child elements)
        if (!e.currentTarget.contains(e.relatedTarget)) {
            setDragOverSubmittalId(null);
            setDragOverHalf(null);
        }
    }, []);

    const handleDragEnd = useCallback(() => {
        setDraggedRow(null);
        setDragOverSubmittalId(null);
        setDragOverHalf(null);
    }, []);

    const handleDrop = useCallback(async (e, targetRow, displayRows) => {
        e.preventDefault();

        if (!draggedRow) {
            setDraggedRow(null);
            setDragOverSubmittalId(null);
            setDragOverHalf(null);
            return;
        }

        try {
            const draggedId = draggedRow['Submittals Id'] ?? draggedRow.submittal_id;
            const targetId = targetRow['Submittals Id'] ?? targetRow.submittal_id;

            // Determine target zone
            const targetZone = getSubmittalZone(targetRow);

            let targetOrder = null;
            let isNoOp = false;

            if (targetZone === 'ordered') {
                const draggedOrder = parseFloat(draggedRow['ORDER #'] ?? draggedRow.order_number);
                const targetOrderNum = parseFloat(targetRow['ORDER #'] ?? targetRow.order_number);

                // Determine which order number to use based on drop half
                if (dragOverHalf === 'top') {
                    targetOrder = targetOrderNum;
                } else {
                    // Find next ordered row after target in same BIC group
                    const bic = targetRow.ball_in_court ?? targetRow['BIC'] ?? '';
                    const nextOrderedRow = displayRows
                        .filter(r => {
                            const rBic = r.ball_in_court ?? r['BIC'] ?? '';
                            if (String(rBic) !== String(bic)) return false;
                            const rOrder = parseFloat(r['ORDER #'] ?? r.order_number ?? 'NaN');
                            if (Number.isNaN(rOrder) || rOrder < 1) return false;
                            return rOrder > targetOrderNum;
                        })
                        .sort((a, b) => {
                            const aOrder = parseFloat(a['ORDER #'] ?? a.order_number);
                            const bOrder = parseFloat(b['ORDER #'] ?? b.order_number);
                            return aOrder - bOrder;
                        })[0];

                    targetOrder = nextOrderedRow
                        ? parseFloat(nextOrderedRow['ORDER #'] ?? nextOrderedRow.order_number)
                        : null;
                }

                // No-op check for ordered zone
                if (!Number.isNaN(draggedOrder)) {
                    if (draggedOrder === targetOrder) {
                        isNoOp = true;
                    } else if (targetOrder !== null) {
                        // Check if dragged is already immediately after target
                        const nextAfterTarget = displayRows
                            .filter(r => {
                                const rBic = r.ball_in_court ?? r['BIC'] ?? '';
                                const bic = targetRow.ball_in_court ?? targetRow['BIC'] ?? '';
                                if (String(rBic) !== String(bic)) return false;
                                const rOrder = parseFloat(r['ORDER #'] ?? r.order_number ?? 'NaN');
                                if (Number.isNaN(rOrder) || rOrder <= targetOrder) return false;
                                return true;
                            })
                            .sort((a, b) => {
                                const aOrder = parseFloat(a['ORDER #'] ?? a.order_number);
                                const bOrder = parseFloat(b['ORDER #'] ?? b.order_number);
                                return aOrder - bOrder;
                            })[0];

                        if (nextAfterTarget && draggedId === (nextAfterTarget['Submittals Id'] ?? nextAfterTarget.submittal_id)) {
                            isNoOp = true;
                        }
                    }
                }
            } else if (targetZone === 'urgent' || targetZone === 'unordered') {
                // No-op: dragged row already in that zone
                const draggedZone = getSubmittalZone(draggedRow);
                if (draggedZone === targetZone) {
                    isNoOp = true;
                }
            }

            if (isNoOp) {
                setDraggedRow(null);
                setDragOverSubmittalId(null);
                setDragOverHalf(null);
                return;
            }

            // Call API
            await draftingWorkLoadApi.dragReorder(draggedId, targetZone, targetOrder);
            await refetch();
        } catch (error) {
            console.error('Drag reorder failed:', error);
        } finally {
            setDraggedRow(null);
            setDragOverSubmittalId(null);
            setDragOverHalf(null);
        }
    }, [draggedRow, dragOverHalf, refetch]);

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
