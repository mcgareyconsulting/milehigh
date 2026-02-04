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
            const errorMsg = 'Invalid order number';
            setError(errorMsg);
            throw new Error(errorMsg);
        }

        // Block 0 - order numbers must be > 0 or NULL
        if (parsedValue !== null && parsedValue === 0) {
            const errorMsg = 'Order number cannot be 0';
            setError(errorMsg);
            throw new Error(errorMsg);
        }

        // Block negative values
        if (parsedValue !== null && parsedValue < 0) {
            const errorMsg = 'Order number cannot be negative';
            setError(errorMsg);
            throw new Error(errorMsg);
        }

        // Validate decimal values - only allow urgency slots 0.1 through 0.9
        if (parsedValue !== null && parsedValue < 1) {
            // This is a decimal (urgency slot)
            const validUrgencySlots = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9];
            // Round to 1 decimal place to handle floating point precision issues
            const roundedValue = Math.round(parsedValue * 10) / 10;
            
            // Check if the rounded value matches exactly one of the valid slots
            // AND that the original value doesn't have significantly more precision than 1 decimal place
            // (allowing for floating point precision errors)
            const difference = Math.abs(parsedValue - roundedValue);
            const hasMoreThanOneDecimal = difference > 0.0001;
            
            if (!validUrgencySlots.includes(roundedValue) || hasMoreThanOneDecimal) {
                const errorMsg = 'Decimal order numbers must be one of: 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9 (urgency slots only)';
                setError(errorMsg);
                throw new Error(errorMsg);
            }
        }

        // Block decimals >= 1.0 (like 1.5, 2.3, etc.)
        if (parsedValue !== null && parsedValue >= 1 && parsedValue !== Math.floor(parsedValue)) {
            const errorMsg = 'Order numbers >= 1 must be whole numbers (no decimals)';
            setError(errorMsg);
            throw new Error(errorMsg);
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