import { useState, useCallback, useEffect } from 'react';
import { jobsApi } from '../services/jobsApi';

export function useJobsDataFetching() {
    const [jobs, setJobs] = useState([]);
    const [columns, setColumns] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [lastUpdated, setLastUpdated] = useState(null);

    const fetchData = useCallback(async (silent = false) => {
        if (!silent) setLoading(true);
        setError(null); // Reset error

        try {
            // Fetch data from API
            const data = await jobsApi.fetchData();

            // Extract jobs array
            let jobsList = data.jobs || [];

            // Sort by Job # ascending, then Release # ascending
            jobsList = jobsList.sort((a, b) => {
                // First sort by Job #
                if (a['Job #'] !== b['Job #']) {
                    return (a['Job #'] || 0) - (b['Job #'] || 0);
                }
                // Then sort by Release # (treat as string for comparison)
                const releaseA = String(a['Release #'] || '').toLowerCase();
                const releaseB = String(b['Release #'] || '').toLowerCase();
                return releaseA.localeCompare(releaseB);
            });

            // Get columns from first job if available
            const jobColumns = jobsList.length > 0
                ? Object.keys(jobsList[0]).filter(key => key !== 'id')
                : [];

            // Update state
            setJobs(jobsList);
            setColumns(jobColumns);
            setLastUpdated(new Date().toISOString());

        } catch (error) {
            console.error('Error fetching jobs data:', error);
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
        jobs,
        columns,
        loading,
        error,
        lastUpdated,
        refetch: fetchData,
    };
}

