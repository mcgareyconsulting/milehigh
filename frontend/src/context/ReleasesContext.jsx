/**
 * @milehigh-header
 * schema_version: 1
 * purpose: App-level store for the releases dataset — lifts the cursor-merge + 30s polling engine out of useJobsDataFetching so Job Log, PM Board, and the Timeline share one load that survives navigation.
 * exports:
 *   ReleasesProvider: Provider that fetches all releases once (gated on `enabled`) then polls; holds jobs/columns/loading/error/lastUpdated
 *   useReleases: Accessor hook (throws outside the provider); returns the same shape the old useJobsDataFetching hook returned
 *   mergeJobs: Pure cursor-merge reducer (add/update/soft-delete/archive removal + id sort) — exported for unit tests
 * imports_from: [react, ../services/jobsApi]
 * imported_by: [../components/AppShell.jsx, ../pages/ReleasesLayout.jsx, ../components/GanttChart.jsx]
 * invariants:
 *   - Cursor timestamp is persisted in localStorage (key jobLogCursorTimestamp); initial mount fetches all pages then sets the cursor
 *   - Polling pauses when the browser tab is hidden and resumes with an immediate fetch on visibility
 *   - Soft-deleted or archived jobs (is_active=false / is_archived=true) are removed from the in-memory array on merge
 *   - Initial fetch + polling only run while `enabled` is true (prevents 401 spam before login)
 */
import { createContext, useContext, useState, useCallback, useEffect, useRef, useMemo } from 'react';
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

/**
 * Merge a batch of new/updated jobs from a cursor poll into the previous array.
 *
 * Pure reducer extracted from the old useJobsDataFetching merge block so it can
 * be unit tested. Semantics are unchanged:
 *  - empty incoming → return prevJobs unchanged (referential no-op)
 *  - is_active=false or is_archived=true → remove that id from the array
 *  - otherwise add/update by id
 *  - result sorted ascending by id for stable order
 */
export function mergeJobs(prevJobs, incomingJobs) {
    const newJobsList = incomingJobs || [];
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
        if (newJob.is_active === false || newJob.is_archived === true) {
            // Soft-deleted or archived — remove from active job log
            if (jobsMap.has(newJob.id)) {
                jobsMap.delete(newJob.id);
                console.log(`[CURSOR] Removing ${newJob.is_archived ? 'archived' : 'deleted'} job: id=${newJob.id}, Job #=${newJob['Job #']}, Release #=${newJob['Release #']}`);
            }
            return;
        }
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
}

const ReleasesContext = createContext(null);

// Synthetic Job Log column (not a backend release field): the material-order
// status rollup is fetched separately and merged onto each row under this key.
const MATERIAL_STATUS_COLUMN = 'Mat. Ord.';

export function ReleasesProvider({ children, enabled = true }) {
    const [jobs, setJobs] = useState([]);
    const [columns, setColumns] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [lastUpdated, setLastUpdated] = useState(null);
    const hasFetchedAllRef = useRef(false);
    // Sparse map "job-release" → 'received'|'pending'|'overdue' for releases that
    // have material orders. Refreshed alongside the release poll.
    const [materialStatus, setMaterialStatus] = useState({});
    const lastSummaryJsonRef = useRef('');

    const fetchMaterialSummary = useCallback(async () => {
        try {
            const summary = await jobsApi.getMaterialOrderSummary();
            const json = JSON.stringify(summary);
            // Only churn state when the rollup actually changed, so a no-op poll
            // keeps the merged jobs array referentially stable (no needless re-render).
            if (json === lastSummaryJsonRef.current) return;
            lastSummaryJsonRef.current = json;
            const map = {};
            for (const s of summary) map[`${s.job}-${s.release}`] = s.status;
            setMaterialStatus(map);
        } catch (err) {
            console.warn('[MATERIAL] Failed to fetch material order summary:', err);
        }
    }, []);

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
                // No latest_timestamp but jobs were returned — shouldn't happen;
                // log and leave the cursor untouched so the next poll retries.
                console.warn('[CURSOR] No latest_timestamp in response, but jobs were returned');
            }

            // Merge new/updated jobs into existing jobs array
            setJobs(prevJobs => mergeJobs(prevJobs, newJobsList));

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

    // Fetch all jobs on mount (paginated to get complete dataset).
    // Gated on `enabled` so no /brain/* requests fire before login.
    useEffect(() => {
        if (!enabled) {
            // Provider survives logout (AppShell stays mounted), so reset the
            // guard — the next login must re-sync the full dataset instead of
            // serving the previous session's snapshot.
            hasFetchedAllRef.current = false;
            return;
        }
        // Use ref to prevent duplicate fetches (handles React Strict Mode double-invocation)
        if (!hasFetchedAllRef.current) {
            hasFetchedAllRef.current = true;
            fetchAllData();
            fetchMaterialSummary();
        }
    }, [enabled, fetchAllData, fetchMaterialSummary]);

    // Poll for updates every 30 seconds, pauses when tab is not visible to save resources
    useEffect(() => {
        if (!enabled) return;
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
                    fetchMaterialSummary();
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
                fetchMaterialSummary();
            }
        };

        // Only start polling if this tab is visible (avoids timer running in background if page opened in background tab)
        if (!document.hidden) {
            startPolling();
        }

        document.addEventListener('visibilitychange', visibilityChangeHandler);

        // Cleanup
        return () => {
            stopPolling();
            document.removeEventListener('visibilitychange', visibilityChangeHandler);
        };
    }, [enabled, fetchData, fetchMaterialSummary]);

    // Merge the material-order status onto each row under the synthetic column key.
    // A release with no orders gets null → the Job Log renders a blank cell.
    const jobsWithMaterial = useMemo(
        () => jobs.map(job => ({
            ...job,
            [MATERIAL_STATUS_COLUMN]:
                materialStatus[`${job['Job #']}-${job['Release #']}`] ?? null,
        })),
        [jobs, materialStatus]
    );

    // Advertise the synthetic column so the Job Log header/filter picks it up
    // (display order still comes from columnOrder in jobLogColumns.js).
    const columnsWithMaterial = useMemo(
        () => (columns.includes(MATERIAL_STATUS_COLUMN)
            ? columns
            : [...columns, MATERIAL_STATUS_COLUMN]),
        [columns]
    );

    const value = useMemo(() => ({
        jobs: jobsWithMaterial,
        columns: columnsWithMaterial,
        loading,
        error,
        lastUpdated,
        refetch: fetchData,
        fetchAll: fetchAllData,
        refreshMaterialSummary: fetchMaterialSummary,
    }), [jobsWithMaterial, columnsWithMaterial, loading, error, lastUpdated, fetchData, fetchAllData, fetchMaterialSummary]);

    return (
        <ReleasesContext.Provider value={value}>
            {children}
        </ReleasesContext.Provider>
    );
}

export function useReleases() {
    const ctx = useContext(ReleasesContext);
    if (ctx === null) {
        throw new Error('useReleases must be used within a ReleasesProvider');
    }
    return ctx;
}
