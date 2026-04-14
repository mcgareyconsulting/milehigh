/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Fetches, transforms, and polls DWL (Drafting Work Load) submittal data so the DraftingWorkLoad page stays current without manual refresh.
 * exports:
 *   useDataFetching: Named export — hook returning { submittals, columns, loading, error, lastUpdated, refetch }
 * imports_from: [react, ../services/draftingWorkLoadApi, ../utils/transformers, ../utils/sorting, ../utils/columns]
 * imported_by: [frontend/src/pages/DraftingWorkLoad.jsx]
 * invariants:
 *   - Polls every 30 seconds; pauses when document is hidden and fetches immediately on visibility restore.
 *   - locationFilter and tab are tracked via refs so the poller always uses current values without restarting the interval.
 * updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
 */
import { useState, useCallback, useEffect, useRef } from 'react';
import { draftingWorkLoadApi } from '../services/draftingWorkLoadApi';
import { transformSubmittals, getMostRecentUpdate } from '../utils/transformers';
import { sortByOrderNumber } from '../utils/sorting';
import { getVisibleColumns } from '../utils/columns';

/**
 * @param { { lat: number, lng: number } | null } locationFilter - when set, DWL is filtered by job_sites containing this point
 * @param { 'open' | 'draft' | 'all' } tab - 'open' = Open status submittals; 'draft' = submittals not Open or Closed; 'all' = both tabs merged
 */
export function useDataFetching(locationFilter = null, tab = 'open') {
    const [submittals, setSubmittals] = useState([]);
    const [columns, setColumns] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [lastUpdated, setLastUpdated] = useState(null);

    // Ref so the 30s poller always uses current lat/lng and tab
    const locationFilterRef = useRef(locationFilter);
    const tabRef = useRef(tab);
    useEffect(() => {
        locationFilterRef.current = locationFilter;
    }, [locationFilter]);
    useEffect(() => {
        tabRef.current = tab;
    }, [tab]);

    const fetchData = useCallback(async (silent = false) => {
        if (!silent) setLoading(true);
        setError(null); // Reset error

        try {
            const currentFilter = locationFilterRef.current;
            const currentTab = tabRef.current;
            const data = await draftingWorkLoadApi.fetchData(currentFilter, currentTab);

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
    }, [locationFilter, tab]);


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