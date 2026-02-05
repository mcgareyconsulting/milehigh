import { useState, useCallback } from 'react';
import { draftingWorkLoadApi } from '../services/draftingWorkLoadApi';

export function useMutations(refetch) {
    const [updating, setUpdating] = useState(false);
    const [error, setError] = useState(null);
    const [success, setSuccess] = useState(false);

    const executeMutation = useCallback(async (apiCall, errorMessage) => {
        setUpdating(true);
        setError(null);
        setSuccess(false);

        try {
            await apiCall();
            setSuccess(true);
            if (refetch) await refetch(true);
        } catch (err) {
            console.error(errorMessage, err);
            setError(err.message);
            if (refetch) {
                try {
                    await refetch(true);
                } catch (refetchErr) {
                    console.error('Refetch failed:', refetchErr);
                }
            }
        } finally {
            setUpdating(false);
        }
    }, [refetch]);

    const updateOrderNumber = useCallback(async (submittalId, orderNumber) => {
        // Handle dash, blank, empty string, null, or undefined as NULL (clear order number)
        const trimmedValue = typeof orderNumber === 'string' ? orderNumber.trim() : orderNumber;
        const isClearValue = trimmedValue === '' ||
            trimmedValue === '-' ||
            trimmedValue === null ||
            trimmedValue === undefined;

        const parsedValue = isClearValue
            ? null
            : parseFloat(trimmedValue);

        if (parsedValue !== null && isNaN(parsedValue)) {
            setError('Invalid order number');
            return;
        }

        // Block 0 - order numbers must be > 0 or NULL
        if (parsedValue !== null && parsedValue === 0) {
            setError('Order number cannot be 0');
            return;
        }

        // Validate urgency slots: if < 1, must be exactly 0.1, 0.2, ..., 0.9
        if (parsedValue !== null && parsedValue > 0 && parsedValue < 1) {
            // Round to nearest tenth
            const rounded = Math.round(parsedValue * 10) / 10;
            const validUrgencySlots = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9];
            if (!validUrgencySlots.includes(rounded)) {
                setError('Urgency slots must be exactly 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, or 0.9');
                return;
            }
            // Use the rounded value
            const finalValue = rounded;
            await executeMutation(
                () => draftingWorkLoadApi.updateOrderNumber(submittalId, finalValue),
                `Failed to update order number for submittal ${submittalId}`
            );
            return;
        }

        await executeMutation(
            () => draftingWorkLoadApi.updateOrderNumber(submittalId, parsedValue),
            `Failed to update order number for submittal ${submittalId}`
        );
    }, [executeMutation]);

    const updateNotes = useCallback(async (submittalId, notes) => {
        await executeMutation(
            () => draftingWorkLoadApi.updateNotes(submittalId, notes),
            `Failed to update notes for submittal ${submittalId}`
        );
    }, [executeMutation]);

    const updateStatus = useCallback(async (submittalId, status) => {
        await executeMutation(
            () => draftingWorkLoadApi.updateStatus(submittalId, status),
            `Failed to update status for submittal ${submittalId}`
        );
    }, [executeMutation]);

    const bumpSubmittal = useCallback(async (submittalId) => {
        await executeMutation(
            () => draftingWorkLoadApi.bumpSubmittal(submittalId),
            `Failed to bump submittal ${submittalId}`
        );
    }, [executeMutation]);

    const updateDueDate = useCallback(async (submittalId, dueDate) => {
        await executeMutation(
            () => draftingWorkLoadApi.updateDueDate(submittalId, dueDate),
            `Failed to update due date for submittal ${submittalId}`
        );
    }, [executeMutation]);

    return {
        // Order number mutation
        updateOrderNumber,
        updating,
        error,
        success,

        // Notes mutation
        updateNotes,

        // Status mutation
        updateStatus,

        // Bump mutation
        bumpSubmittal,

        // Due date mutation
        updateDueDate,
    };
}