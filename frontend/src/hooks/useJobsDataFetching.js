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

            console.log('Raw data:', data);

            // Log metadata instead of full data (avoids console truncation)
            const isDataArray = Array.isArray(data);
            const firstItem = isDataArray && data.length > 0 ? data[0] : null;
            const firstItemKeys = firstItem && typeof firstItem === 'object' ? Object.keys(firstItem) : null;

            console.log('Data received:', {
                hasData: !!data,
                dataType: typeof data,
                isArray: isDataArray,
                arrayLength: isDataArray ? data.length : null,
                firstItemType: firstItem ? typeof firstItem : null,
                firstItemIsObject: firstItem ? typeof firstItem === 'object' : null,
                firstItemKeys: firstItemKeys,
                jobsType: typeof data?.jobs,
                jobsIsArray: Array.isArray(data?.jobs),
                jobsLength: data?.jobs?.length
            });

            // Check if this looks like a jobs array or something else
            if (isDataArray && firstItem) {
                console.log('First array item sample:', {
                    hasId: 'id' in firstItem,
                    hasJob: 'Job #' in firstItem || 'Job' in firstItem,
                    keys: firstItemKeys?.slice(0, 10)
                });
            }

            // Extract jobs array - handle both {jobs: [...]} and direct array
            let jobsList = [];
            if (isDataArray) {
                // If data is directly an array
                // Check if first item looks like a job object
                if (firstItem && typeof firstItem === 'object' && ('Job #' in firstItem || 'id' in firstItem)) {
                    console.log('Data is an array of job objects with', data.length, 'items. Using directly.');
                    jobsList = data;
                } else {
                    // Array but doesn't look like jobs - might be malformed
                    console.error('Data is array but items dont look like jobs. First item:', firstItem);
                    console.error('Expected job object with "Job #" or "id" key');
                }
            } else if (data && data.jobs) {
                // Normal case: { jobs: [...] }
                console.log('Data is object with jobs property. Extracting jobs array.');
                jobsList = Array.isArray(data.jobs) ? data.jobs : [];
            } else if (data && typeof data === 'object') {
                // Fallback: check if data has any array-like structure
                console.warn('Unexpected data structure. Data keys:', Object.keys(data).slice(0, 20));
            } else {
                console.warn('Data is not in expected format:', typeof data);
            }

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

