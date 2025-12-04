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


    // Fetch data on mount
    useEffect(() => {
        fetchData();
    }, [fetchData]);

    // Poll for updates every 30 seconds, pauses when tab is not visible to save resources
    useEffect(() => {
        let intervalId = null;
        let visibilityChangeHandler = null;

        const startPolling = () => {
            // Clear any existing interval
            if (intervalId) {
                clearInterval(intervalId);
            }

            intervalId = setInterval(() => {
                if (!document.hidden) {
                    fetchData(true);
                }
            }, 30000);
        }

        const stopPolling = () => {
            if (intervalId) {
                clearInterval(intervalId);
                intervalId = null;
            }
        };

        visibilityChangeHandler = () => {
            if (document.hidden) {
                stopPolling();
            } else {
                startPolling();
                fetchData(true); // Immediately fetch when tab becomes visible
            }
        };

        // Start polling
        startPolling();

        document.addEventListener('visibilitychange', visibilityChangeHandler);

        // Cleanup
        return () => {
            stopPolling();
            document.removeEventListener('visibilitychange', visibilityChangeHandler);
        };
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