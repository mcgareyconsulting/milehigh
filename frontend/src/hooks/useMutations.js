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
        const parsedValue = orderNumber === '' || orderNumber === null || orderNumber === undefined
            ? null
            : parseFloat(orderNumber);

        if (parsedValue !== null && isNaN(parsedValue)) {
            setError('Invalid order number');
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

        // Upload mutation
        uploadFile,
        uploading,
        uploadError,
        uploadSuccess,
        clearUploadSuccess,
    };
}