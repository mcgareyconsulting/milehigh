/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Wraps all DWL field-update API calls with unified loading/error/success state so each mutation is a one-liner in the page.
 * exports:
 *   useMutations: Hook returning mutation functions (updateOrderNumber, updateNotes, updateStatus, etc.) with shared updating/error/success state
 * imports_from: [react, ../services/draftingWorkLoadApi]
 * imported_by: [../pages/DraftingWorkLoad.jsx]
 * invariants:
 *   - Order number 0 is treated as clear (NULL / unordered); values between 0-1 must be exact tenths (0.1-0.9)
 *   - Every mutation triggers refetch(true) on both success and failure to keep UI in sync
 *   - Dash, blank, empty string, null, undefined, and 0 all clear the order number to NULL
 * updated_by_agent: 2026-08-06T00:00:00Z
 */
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
        // Clear = unordered: dash, blank, null, undefined, or 0 (BUG-2: uncheck 1 → 0)
        const trimmedValue = typeof orderNumber === 'string' ? orderNumber.trim() : orderNumber;
        const isClearValue = trimmedValue === '' ||
            trimmedValue === '-' ||
            trimmedValue === null ||
            trimmedValue === undefined ||
            trimmedValue === 0 ||
            trimmedValue === '0';

        let parsedValue = isClearValue
            ? null
            : parseFloat(trimmedValue);

        if (parsedValue !== null && isNaN(parsedValue)) {
            setError('Invalid order number');
            return;
        }

        // 0 means "no order" — same as blank. Never store 0 in the DB.
        if (parsedValue === 0) {
            parsedValue = null;
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

    const updateDueDate = useCallback(async (submittalId, dueDate, gcJobsiteScheduleDate) => {
        await executeMutation(
            () => draftingWorkLoadApi.updateDueDate(submittalId, dueDate, gcJobsiteScheduleDate),
            `Failed to update due date for submittal ${submittalId}`
        );
    }, [executeMutation]);

    const updateStartInstall = useCallback(async (submittalId, startInstall, dueDate) => {
        await executeMutation(
            () => draftingWorkLoadApi.updateStartInstall(submittalId, startInstall, dueDate),
            `Failed to update start install for submittal ${submittalId}`
        );
    }, [executeMutation]);

    const updateProcoreStatus = useCallback(async (submittalId, statusId) => {
        await executeMutation(
            () => draftingWorkLoadApi.updateProcoreStatus(submittalId, statusId),
            `Failed to update Procore status for submittal ${submittalId}`
        );
    }, [executeMutation]);

    const stepSubmittal = useCallback(async (submittalId, direction) => {
        await executeMutation(
            () => draftingWorkLoadApi.stepOrder(submittalId, direction),
            `Failed to step submittal ${submittalId} ${direction}`
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

        // Procore status mutation (Draft/Open/Closed etc.)
        updateProcoreStatus,

        // Bump mutation
        bumpSubmittal,

        // Due date mutation
        updateDueDate,

        // Start install mutation (DWL → job log handoff)
        updateStartInstall,

        // Step mutation (up/down arrows)
        stepSubmittal,
    };
}