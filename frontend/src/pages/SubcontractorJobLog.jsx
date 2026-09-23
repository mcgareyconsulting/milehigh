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
import { getSubDaySchedule, getSubReleases, listSubTodos } from '../services/subPortalApi';

const POLL_MS = 60000;

function UnscheduledCard({ rel, onOpen }) {
    const code = `${rel['Job #']}-${rel['Release #']}`;
    return (
        <button type="button" onClick={() => onOpen(rel.id)}
            className="w-full text-left rounded-lg border border-hairline bg-surface shadow-sm p-3 active:scale-[0.995]">
            <div className="flex items-start justify-between gap-2">
                <span className="font-mono text-sm font-bold text-accent-600 dark:text-accent-400">{code}</span>
                {rel.Stage && <span className="text-[11px] text-ink-3 truncate max-w-[10rem]">{rel.Stage}</span>}
            </div>
            {rel.Job && <div className="mt-0.5 text-sm font-medium text-ink break-words">{rel.Job}</div>}
            {rel.Description && <div className="mt-1 text-xs text-ink-2 line-clamp-2 break-words">{rel.Description}</div>}
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

    return (
        <div className="flex-1 min-h-0 flex flex-col p-3 gap-2">
            <div className="flex items-baseline justify-between gap-2 px-1">
                <h1 className="text-base font-bold text-ink">Job Log</h1>
                <span className="text-xs text-ink-3 truncate">{crew ? `${crew} · next 2 weeks` : 'No crew assigned yet'}</span>
            </div>

            {!crew && (
                <p className="rounded-lg border border-amber-300 bg-amber-50 text-amber-800 dark:bg-amber-900/30 dark:text-amber-200 dark:border-amber-700 px-3 py-2 text-sm">
                    Your account is not linked to a crew yet, so there is nothing to show. Ask MHMW to assign your crew.
                </p>
            )}
            {loading && <div className="text-ink-3 text-sm px-1">Loading your schedule…</div>}
            {error && <div className="text-red-600 dark:text-red-400 text-sm px-1">{error}</div>}

            {!loading && !error && data && (
                <DaySchedule data={data} roster={roster} crewFilter={crew} onOpenRelease={openCard} />
            )}

            {!loading && !error && unscheduled.length > 0 && (
                <section className="mt-1">
                    <button type="button" onClick={() => setShowUnscheduled((v) => !v)}
                        className="w-full flex items-center justify-between px-1 py-2 text-xs font-extrabold uppercase tracking-wide text-ink-3">
                        <span>Not yet scheduled · {unscheduled.length}</span>
                        <span aria-hidden="true">{showUnscheduled ? '▾' : '▸'}</span>
                    </button>
                    {showUnscheduled && (
                        <div className="flex flex-col gap-2 pb-3">
                            {unscheduled.map((r) => <UnscheduledCard key={r.id} rel={r} onOpen={setOpenId} />)}
                        </div>
                    )}
                </section>
            )}

            <SubReleaseSheet releaseId={openId} onClose={closeSheet} todos={todos} />
        </div>
    );
}
