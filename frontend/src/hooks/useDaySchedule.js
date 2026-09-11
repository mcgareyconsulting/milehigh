/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Fetch state for the day-row installation schedule, shared by the two surfaces that show
 *   it — the Installation Schedule page and the Job Log's Timeline on a phone. The Timeline used to
 *   send phones away to /install-schedule; keeping the fetch in a hook is what lets the same vertical
 *   calendar render in place instead, so the Timeline stays the Timeline.
 * exports:
 *   useDaySchedule: ({days, pastDays, installer, enabled})
 *     -> {data, loading, error, reload, roster, crewOptions}
 *   useReleaseHub: () -> {hubJob, openRelease, closeHub} — resolves a schedule card to a full
 *     job-log row for the shared release modal.
 * imports_from: [react, ../services/installScheduleApi, ../services/jobsApi, ../context/ReleasesContext,
 *   ../utils/crewColor]
 * imported_by: [../pages/InstallSchedule.jsx, ../pages/PMBoardContent.jsx]
 * invariants:
 *   - The roster is fetched once and only fixes CREW COLOUR ordering (utils/crewColor). A failure is
 *     swallowed: colours fall back to discovery order, which is not worth failing a page over.
 *   - openRelease resolves the card's release_id against the shared ReleasesContext, because the
 *     schedule payload is deliberately slim and the hub wants the whole row. When the row isn't
 *     loaded (archived, or a partial first page) it still opens on the bare identifiers — a tap that
 *     silently does nothing is worse than a modal with a thinner header.
 *   - `enabled` exists so a surface that is not currently showing the calendar does not poll for it.
 *   - crewOptions is built from the ROSTER, plus every crew seen in any response so far — never from
 *     the current response alone. The payload is filtered, so `summary.crews` narrows to the selected
 *     crew; a picker built from it would collapse to one option the moment you used it. Names seen
 *     under an earlier filter are therefore remembered, not dropped.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { getDaySchedule } from '../services/installScheduleApi';
import { jobsApi } from '../services/jobsApi';
import { useReleases } from '../context/ReleasesContext';
import { crewFilterOptions } from '../utils/crewColor';

export function useDaySchedule({ days = 14, pastDays = 14, installer = null, enabled = true } = {}) {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(enabled);
    const [error, setError] = useState(null);
    const [roster, setRoster] = useState([]);
    // Union of every crew any response has mentioned; only ever grows (see invariants).
    const [seenCrews, setSeenCrews] = useState([]);

    useEffect(() => {
        let cancelled = false;
        jobsApi.getInstallerTeams()
            .then((teams) => { if (!cancelled) setRoster(teams); })
            .catch(() => { /* colours fall back to discovery order */ });
        return () => { cancelled = true; };
    }, []);

    const reload = useCallback(async () => {
        if (!enabled) return;
        setLoading(true);
        setError(null);
        try {
            const envelope = await getDaySchedule({ days, pastDays, installer });
            setData(envelope);
            const crews = envelope?.summary?.crews || [];
            setSeenCrews((prev) => {
                const next = crews.filter((c) => !prev.includes(c));
                return next.length ? [...prev, ...next] : prev;
            });
        } catch (e) {
            setError(e?.response?.data?.error || e.message || 'Failed to load schedule');
        } finally {
            setLoading(false);
        }
    }, [days, pastDays, installer, enabled]);

    useEffect(() => { reload(); }, [reload]);

    const crewOptions = useMemo(() => crewFilterOptions(roster, seenCrews), [roster, seenCrews]);

    return { data, loading, error, reload, roster, crewOptions };
}

export function useReleaseHub() {
    const { jobs } = useReleases();
    const [hubJob, setHubJob] = useState(null);

    const openRelease = useCallback((card) => {
        const row = jobs.find((j) => j.id === card.release_id);
        setHubJob(row || { id: card.release_id, job: card.job, release: card.release });
    }, [jobs]);

    const closeHub = useCallback(() => setHubJob(null), []);

    return { hubJob, openRelease, closeHub };
}
