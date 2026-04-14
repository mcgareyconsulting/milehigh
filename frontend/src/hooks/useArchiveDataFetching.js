/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Fetches and caches archived job data so the Archive page can render without re-fetching on every mount.
 * exports:
 *   useArchiveDataFetching: Hook returning archived jobs, columns, loading/error state, and a refetch handle
 * imports_from: [react, ../services/jobsApi]
 * imported_by: [../pages/Archive.jsx]
 * invariants:
 *   - Only fetches once per mount via hasFetchedRef guard (React Strict Mode safe)
 *   - Always passes true to jobsApi.fetchAllJobs to request archived jobs only
 * updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
 */
import { useState, useCallback, useEffect, useRef } from 'react';
import { jobsApi } from '../services/jobsApi';

export function useArchiveDataFetching() {
    const [jobs, setJobs] = useState([]);
    const [columns, setColumns] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const hasFetchedRef = useRef(false);

    const fetchAll = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            console.log('[ARCHIVE] Fetching all archived jobs...');
            const allJobs = await jobsApi.fetchAllJobs(true);
            console.log(`[ARCHIVE] Fetched ${allJobs.length} archived jobs`);

            setJobs(allJobs);
            setColumns(allJobs.length > 0 ? Object.keys(allJobs[0]).filter(k => k !== 'id') : []);
        } catch (err) {
            console.error('[ARCHIVE] Error fetching archived jobs:', err);
            setError(err.message);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        if (!hasFetchedRef.current) {
            hasFetchedRef.current = true;
            fetchAll();
        }
    }, [fetchAll]);

    return { jobs, columns, loading, error, refetch: fetchAll };
}
