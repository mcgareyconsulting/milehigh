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

            // Log metadata instead of full data (avoids console truncation)
            console.log('Data received:', {
                hasData: !!data,
                dataKeys: data ? Object.keys(data) : [],
                jobsType: typeof data?.jobs,
                jobsIsArray: Array.isArray(data?.jobs),
                jobsLength: data?.jobs?.length,
                firstJobSample: data?.jobs?.[0] ? Object.keys(data.jobs[0]) : null
            });

            // Extract jobs array - same pattern as drafting-work-load
            const jobsList = data.jobs || [];

            console.log('Jobs list extracted:', {
                length: jobsList.length,
                isArray: Array.isArray(jobsList),
                firstItemKeys: jobsList[0] ? Object.keys(jobsList[0]) : null
            });

            // Get columns from first job if available
            const jobColumns = jobsList.length > 0
                ? Object.keys(jobsList[0]).filter(key => key !== 'id')
                : [];

            console.log('About to set state:', {
                jobsCount: jobsList.length,
                columnsCount: jobColumns.length
            });

            // Update state
            setJobs(jobsList);
            setColumns(jobColumns);
            setLastUpdated(new Date().toISOString());

            console.log('State updated successfully');

            // Debug: Log if jobs list is empty but data exists (production debugging)
            if (jobsList.length === 0 && data && Object.keys(data).length > 0) {
                console.warn('useJobsDataFetching: Jobs list is empty. Data keys:', Object.keys(data), 'data.jobs type:', typeof data.jobs);
            }

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

    // Log when state actually updates
    useEffect(() => {
        console.log('Jobs state updated:', {
            jobsCount: jobs.length,
            columnsCount: columns.length,
            loading,
            error,
            sampleJob: jobs[0] ? Object.keys(jobs[0]) : null
        });
    }, [jobs, columns, loading, error]);

    return {
        jobs,
        columns,
        loading,
        error,
        lastUpdated,
        refetch: fetchData,
    };
}

