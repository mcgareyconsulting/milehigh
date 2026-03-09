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
