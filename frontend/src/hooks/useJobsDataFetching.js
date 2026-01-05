import { useState, useCallback, useEffect, useRef } from 'react';
import { jobsApi } from '../services/jobsApi';

// localStorage keys
const CURSOR_TIMESTAMP_KEY = 'jobLogCursorTimestamp';

// Helper functions for localStorage cursor
const getCursorTimestamp = () => {
    const stored = localStorage.getItem(CURSOR_TIMESTAMP_KEY);
    return stored || null;
};

const setCursorTimestamp = (timestamp) => {
    if (timestamp) {
        localStorage.setItem(CURSOR_TIMESTAMP_KEY, timestamp);
    } else {
        localStorage.removeItem(CURSOR_TIMESTAMP_KEY);
    }
};

export function useJobsDataFetching() {
    const [jobs, setJobs] = useState([]);
    const [columns, setColumns] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [lastUpdated, setLastUpdated] = useState(null);
    const hasFetchedAllRef = useRef(false);

    const fetchData = useCallback(async (silent = false) => {
        if (!silent) setLoading(true);
        setError(null); // Reset error

        try {
            // Get cursor timestamp from localStorage
            const cursorTimestamp = getCursorTimestamp();
            console.log('[CURSOR] Polling for new/updated jobs...', cursorTimestamp ? `since ${cursorTimestamp}` : '(initial load)');

            // Fetch data from API (only new/updated jobs since last cursor)
            const data = await jobsApi.fetchData(cursorTimestamp);

            // Extract jobs array - these are only new/updated jobs
            const newJobsList = data.jobs || [];
            console.log(`[CURSOR] Received ${newJobsList.length} new/updated jobs from API`);

            // Update cursor timestamp if we got a latest_timestamp from the server
            if (data.latest_timestamp) {
                setCursorTimestamp(data.latest_timestamp);
                console.log(`[CURSOR] Updated cursor timestamp to: ${data.latest_timestamp}`);
            } else if (newJobsList.length > 0) {
                // If no latest_timestamp but we have jobs, use the last job's timestamp
                // This shouldn't happen, but handle it gracefully
                const lastJob = newJobsList[newJobsList.length - 1];
                // Note: We'd need to get the actual last_updated_at from the job if available
                console.warn('[CURSOR] No latest_timestamp in response, but jobs were returned');
            }

            // Merge new/updated jobs into existing jobs array
            setJobs(prevJobs => {
                const prevCount = prevJobs.length;

                if (newJobsList.length === 0) {
                    // No new jobs, return existing array unchanged
                    console.log('[CURSOR] No new jobs, keeping existing array unchanged');
                    return prevJobs;
                }

                // Create a map of existing jobs by ID for quick lookup
                const jobsMap = new Map(prevJobs.map(job => [job.id, job]));
                const existingIds = new Set(prevJobs.map(job => job.id));

                let addedCount = 0;
                let updatedCount = 0;

                // Update or add jobs from the new list
                newJobsList.forEach(newJob => {
                    if (existingIds.has(newJob.id)) {
                        updatedCount++;
                        console.log(`[CURSOR] Updating existing job: id=${newJob.id}, Job #=${newJob['Job #']}, Release #=${newJob['Release #']}`);
                    } else {
                        addedCount++;
                        console.log(`[CURSOR] Adding new job: id=${newJob.id}, Job #=${newJob['Job #']}, Release #=${newJob['Release #']}`);
                    }
                    jobsMap.set(newJob.id, newJob);
                });

                // Convert map back to array, maintaining order
                const mergedJobs = Array.from(jobsMap.values());

                // Sort by id to maintain consistent order
                mergedJobs.sort((a, b) => (a.id || 0) - (b.id || 0));

                console.log(`[CURSOR] Merge complete: ${prevCount} -> ${mergedJobs.length} jobs (${addedCount} added, ${updatedCount} updated)`);

                return mergedJobs;
            });

            // Get columns from first job if available (use existing or new)
            if (newJobsList.length > 0) {
                const jobColumns = Object.keys(newJobsList[0]).filter(key => key !== 'id');
                setColumns(jobColumns);
            }

            setLastUpdated(new Date().toISOString());

        } catch (error) {
            console.error('[CURSOR] Error fetching jobs data:', error);
            setError(error.message);
        } finally {
            if (!silent) setLoading(false);
        }
    }, []);

    const fetchAllData = useCallback(async (silent = false) => {
        if (!silent) setLoading(true);
        setError(null); // Reset error

        try {
            console.log('[CURSOR] Initial mount: Fetching all jobs...');

            // Fetch all jobs from API (paginated)
            const allJobs = await jobsApi.fetchAllJobs();
            console.log(`[CURSOR] Initial mount: Fetched ${allJobs.length} total jobs`);

            // Get columns from first job if available
            const jobColumns = allJobs.length > 0
                ? Object.keys(allJobs[0]).filter(key => key !== 'id')
                : [];

            // Update state
            setJobs(allJobs);
            setColumns(jobColumns);
            setLastUpdated(new Date().toISOString());

            // Set cursor after initial fetch completes
            // Make one lightweight call to /jobs without cursor to get the latest_timestamp
            // This establishes the baseline for future polling
            if (allJobs.length > 0) {
                try {
                    console.log('[CURSOR] Initial mount: Getting latest timestamp to set cursor...');
                    // Fetch once without cursor parameter - this will return latest_timestamp
                    // We already have all the jobs, so this is just to get the timestamp
                    const cursorData = await jobsApi.fetchData(null);
                    if (cursorData.latest_timestamp) {
                        setCursorTimestamp(cursorData.latest_timestamp);
                        console.log(`[CURSOR] Initial mount: Cursor set successfully - ${cursorData.latest_timestamp}`);
                    } else {
                        // Fallback: use current time (we've seen everything up to now)
                        const now = new Date().toISOString();
                        setCursorTimestamp(now);
                        console.log(`[CURSOR] Initial mount: No latest_timestamp in response, using current time - ${now}`);
                    }
                } catch (cursorError) {
                    // Log but don't fail the entire fetch if cursor setting fails
                    console.warn('[CURSOR] Initial mount: Failed to set cursor:', cursorError);
                    // Set to current time as fallback
                    const now = new Date().toISOString();
                    setCursorTimestamp(now);
                    console.log(`[CURSOR] Initial mount: Using current time as fallback - ${now}`);
                }
            } else {
                console.log('[CURSOR] Initial mount: No jobs found, cursor not set');
            }

        } catch (error) {
            console.error('[CURSOR] Initial mount: Error fetching all jobs data:', error);
            setError(error.message);
        } finally {
            if (!silent) setLoading(false);
        }
    }, []);

    // Fetch all jobs on mount (paginated to get complete dataset)
    useEffect(() => {
        // Use ref to prevent duplicate fetches (handles React Strict Mode double-invocation)
        if (!hasFetchedAllRef.current) {
            hasFetchedAllRef.current = true;
            fetchAllData();
        }
    }, [fetchAllData]);

    // Poll for updates every 30 seconds, pauses when tab is not visible to save resources
    useEffect(() => {
        let intervalId = null;
        let visibilityChangeHandler = null;

        const startPolling = () => {
            // Clear any existing interval
            if (intervalId) {
                clearInterval(intervalId);
            }

            console.log('[CURSOR] Starting polling interval (30 seconds)');
            intervalId = setInterval(() => {
                if (!document.hidden) {
                    console.log('[CURSOR] Polling interval triggered');
                    fetchData(true);
                } else {
                    console.log('[CURSOR] Tab is hidden, skipping poll');
                }
            }, 30000);
        }

        const stopPolling = () => {
            if (intervalId) {
                clearInterval(intervalId);
                intervalId = null;
                console.log('[CURSOR] Polling stopped');
            }
        };

        visibilityChangeHandler = () => {
            if (document.hidden) {
                console.log('[CURSOR] Tab hidden, stopping polling');
                stopPolling();
            } else {
                console.log('[CURSOR] Tab visible, starting polling and fetching immediately');
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
        fetchAll: fetchAllData,
    };
}

