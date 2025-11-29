import { useCallback } from 'react';
import { draftingWorkLoadApi } from '../services/draftingWorkLoadApi';

export function useMutations(refetch) {
    const updateOrderNumber = useCallback(async (submittalId, orderNumber) => {
        // parse value as float
        const parsedValue = orderNumber === '' || orderNumber === null || orderNumber === undefined
            ? null
            : parseFloat(orderNumber);

        // validate it's a number if not null
        if (parsedValue !== null && isNaN(parsedValue)) {
            throw new Error('Invalid order number');
        }

        try {
            await draftingWorkLoadApi.updateOrderNumber(submittalId, parsedValue);
            if (refetch) await refetch(true);
        } catch (error) {
            console.error(`Failed to update status for submittal ${submittalId}:`, error);
            throw error;
        }
    }, [refetch]);

    return { updateOrderNumber };
}