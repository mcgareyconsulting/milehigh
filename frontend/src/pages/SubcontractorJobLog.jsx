/**
 * @milehigh-header
 * schema_version: 1
 * purpose: The subcontractor's Job Log tab — their crew's Timeline as the phone-shaped vertical
 *          day calendar (the same DaySchedule the staff Timeline shows on a phone), fed by the
 *          sub-scoped by-day endpoint with the crew pinned server-side, plus a "not yet scheduled"
 *          list of crew releases that carry no install date (which the day view cannot show).
 *          Tapping any card opens the read-only SubReleaseSheet.
 * exports:
 *   SubcontractorJobLog: Page component, rendered inside SubcontractorShell's Outlet.
 * imports_from: [react, react-router-dom, ../services/subPortalApi,
 *                ../components/installSchedule/DaySchedule, ../components/sub/SubReleaseSheet]
 * imported_by: [App.jsx]
 * invariants:
 *   - No crew picker: the crew is the account's, chosen by an admin. The header names it so an
 *     empty calendar reads as "nothing scheduled for Saul 2" rather than as a broken page.
 *   - Reuses DaySchedule unchanged (roster = the one crew) — the sub timeline must not grow its own
 *     lane/day logic, or the staff tower work reworks it (ROADMAP T3, 2026-09-07 note).
 *   - Polls while visible so a PM's reschedule shows up without a reload.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import DaySchedule from '../components/installSchedule/DaySchedule';
import SubReleaseSheet from '../components/sub/SubReleaseSheet';
import SubEmpty from '../components/sub/SubEmpty';
import { getSubDaySchedule, getSubReleases, listSubTodos } from '../services/subPortalApi';

const POLL_MS = 60000;

function UnscheduledCard({ rel, onOpen }) {
    const code = `${rel['Job #']}-${rel['Release #']}`;
    return (
        <button type="button" onClick={() => onOpen(rel.id)}
            className="sub-card w-full text-left p-4 active:scale-[0.995]">
            <div className="flex items-start justify-between gap-2">
                <span className="num font-mono text-brand">{code}</span>
                {rel.Stage && <span className="sub-pill truncate max-w-[10rem]">{rel.Stage}</span>}
            </div>
            {rel.Job && <div className="mt-1 text-sm font-bold text-ink break-words">{rel.Job}</div>}
            {rel.Description && <div className="mt-1 text-sm text-ink-3 line-clamp-2 break-words">{rel.Description}</div>}
        </button>
    );
}

export default function SubcontractorJobLog() {
    const { subcontractor } = useOutletContext();
    const crew = subcontractor?.installer_team || null;
    const [data, setData] = useState(null);
    const [releases, setReleases] = useState([]);
    const [todos, setTodos] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [openId, setOpenId] = useState(null);
    const [showUnscheduled, setShowUnscheduled] = useState(false);

    const load = useCallback(async (silent = false) => {
        if (!silent) setLoading(true);
        setError(null);
        try {
            const [env, feed, mine] = await Promise.all([
                getSubDaySchedule({ days: 14, pastDays: 14 }),
                getSubReleases(),
                listSubTodos('all').catch(() => []),
            ]);
            setData(env);
            setReleases(feed.releases || []);
            setTodos(mine);
        } catch (e) {
            setError(e?.response?.data?.error || e.message || 'Failed to load your schedule');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { load(); }, [load]);
    useEffect(() => {
        const t = setInterval(() => { if (document.visibilityState === 'visible') load(true); }, POLL_MS);
        const onVis = () => { if (document.visibilityState === 'visible') load(true); };
        document.addEventListener('visibilitychange', onVis);
        return () => { clearInterval(t); document.removeEventListener('visibilitychange', onVis); };
    }, [load]);

    const unscheduled = useMemo(
        () => releases.filter((r) => !r['Start install'] && r['Job Comp'] !== 'X'),
        [releases],
    );
    const roster = useMemo(() => (crew ? [crew] : []), [crew]);
    const openCard = useCallback((card) => setOpenId(card.release_id), []);
    const closeSheet = useCallback(() => setOpenId(null), []);

    const nothing = data && !data.past_due.length && data.summary.scheduled === 0;

    return (
        <div className="flex-1 min-h-0 flex flex-col">
            <div className="sub-page-head">
                <h1>Job Log</h1>
                <div className="sub-ctx">{crew ? `${crew} · next 2 weeks` : 'No crew assigned'}</div>
            </div>

            {!crew && (
                <SubEmpty icon="calendar" title="No crew assigned yet"
                    body="Your account is not linked to an installer crew, so there is nothing to show. Ask MHMW to assign your crew." />
            )}
            {loading && <div className="text-ink-3 text-sm px-4 py-2">Loading your schedule…</div>}
            {error && <div className="text-red-600 text-sm px-4 py-2">{error}</div>}

            {!loading && !error && crew && nothing && unscheduled.length === 0 && (
                <SubEmpty icon="calendar" title="Nothing scheduled" body={`No installs for ${crew} in the next two weeks.`} />
            )}
            {!loading && !error && data && crew && !nothing && (
                <div className="px-4 flex-1 min-h-0 flex flex-col">
                    <DaySchedule data={data} roster={roster} crewFilter={crew} onOpenRelease={openCard} />
                </div>
            )}

            {!loading && !error && unscheduled.length > 0 && (
                <section className="mt-1 px-4">
                    <button type="button" onClick={() => setShowUnscheduled((v) => !v)}
                        className="w-full flex items-center justify-between px-0 py-2 text-xs font-extrabold uppercase tracking-wide text-ink-3">
                        <span>Not yet scheduled · {unscheduled.length}</span>
                        <span aria-hidden="true">{showUnscheduled ? '▾' : '▸'}</span>
                    </button>
                    {showUnscheduled && (
                        <div className="flex flex-col gap-2.5 pb-4">
                            {unscheduled.map((r) => <UnscheduledCard key={r.id} rel={r} onOpen={setOpenId} />)}
                        </div>
                    )}
                </section>
            )}

            <SubReleaseSheet releaseId={openId} onClose={closeSheet} todos={todos} />
        </div>
    );
}
