import { useState, useCallback } from 'react';
import { draftingWorkLoadApi } from '../services/draftingWorkLoadApi';

export function useMutations(refetch) {
    const [updating, setUpdating] = useState(false);
    const [error, setError] = useState(null);
    const [success, setSuccess] = useState(false);

    // Separate state for upload since it has different UI behavior
    const [uploading, setUploading] = useState(false);
    const [uploadError, setUploadError] = useState(null);
    const [uploadSuccess, setUploadSuccess] = useState(false);

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

    const updateDueDate = useCallback(async (submittalId, dueDate) => {
        await executeMutation(
            () => draftingWorkLoadApi.updateDueDate(submittalId, dueDate),
            `Failed to update due date for submittal ${submittalId}`
        );
    }, [executeMutation]);

    const uploadFile = useCallback(async (file) => {
        setUploading(true);
        setUploadError(null);
        setUploadSuccess(false);

        try {
            await draftingWorkLoadApi.uploadFile(file);
            setUploadSuccess(true);
            setUploadError(null);
            if (refetch) await refetch(true);
        } catch (err) {
            console.error('Failed to upload file:', err);
            setUploadError(err.message);
            setUploadSuccess(false);
        } finally {
            setUploading(false);
        }
    }, [refetch]);

    const clearUploadSuccess = useCallback(() => {
        setUploadSuccess(false);
    }, []);

    const reorderGroup = useCallback(async (ballInCourt) => {
        await executeMutation(
            () => draftingWorkLoadApi.reorderGroup(ballInCourt),
            `Failed to reorder group for ${ballInCourt}`
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

        // Due date mutation
        updateDueDate,

        // Upload mutation
        uploadFile,
        uploading,
        uploadError,
        uploadSuccess,
        clearUploadSuccess,

        // Reorder mutation
        reorderGroup,
    };
}