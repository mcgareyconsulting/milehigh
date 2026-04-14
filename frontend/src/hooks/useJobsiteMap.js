/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Fetches GeoJSON job-site data on mount so the map page can render markers without managing fetch state itself.
 * exports:
 *   useJobsiteMap: Hook returning geojson, loading, and error state for the job-site map
 * imports_from: [react, ../services/jobsiteMapApi]
 * imported_by: [../pages/maps/JobsiteMap.jsx]
 * invariants:
 *   - Fetch is cancelled on unmount via a cancelled flag to prevent state updates on unmounted components
 * updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
 */
import { useState, useEffect } from 'react';
import { jobsiteMapApi } from '../services/jobsiteMapApi';

export function useJobsiteMap() {
    const [geojson, setGeojson] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        let cancelled = false;

        async function fetchData() {
            try {
                setLoading(true);
                setError(null);
                const data = await jobsiteMapApi.fetchMapData();
                if (!cancelled) setGeojson(data);
            } catch (err) {
                if (!cancelled) setError(err.message);
            } finally {
                if (!cancelled) setLoading(false);
            }
        }

        fetchData();
        return () => { cancelled = true; };
    }, []);

    return { geojson, loading, error };
}
