import { useState, useCallback, useEffect } from 'react';
import { draftingWorkLoadApi } from '../services/draftingWorkLoadApi';
import { transformSubmittals, getMostRecentUpdate } from '../utils/transformers';
import { sortByOrderNumber } from '../utils/sorting';
import { getVisibleColumns } from '../utils/columns';

export function useDataFetching() {
    const [submittals, setSubmittals] = useState([]);
    const [columns, setColumns] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [lastUpdated, setLastUpdated] = useState(null);

    const fetchData = useCallback(async (silent = false) => {
        if (!silent) setLoading(true);
        setError(null); // Reset error

        try {
            // Fetch data from API
            const data = await draftingWorkLoadApi.fetchData();

            // Transform data
            const transformed = transformSubmittals(data.submittals);
            const sorted = sortByOrderNumber(transformed);
            const visibleCols = getVisibleColumns(sorted);
            const latestUpdate = getMostRecentUpdate(sorted);

            // Update state
            setSubmittals(sorted);
            setColumns(visibleCols);
            setLastUpdated(latestUpdate);


        } catch (error) {
            console.error('Error fetching drafting work load data:', error);
            setError(error.message);
        } finally {
            if (!silent) setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchData();
    }, [fetchData]);

    return {
        submittals,
        columns,
        loading,
        error,
        lastUpdated,
        refetch: fetchData,
    };
}