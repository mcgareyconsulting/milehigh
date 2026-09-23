/**
 * @milehigh-header
 * schema_version: 1
 * purpose: The subcontractor's Job Log tab — their crew's Timeline as the phone-shaped vertical
 *          day calendar (the same DaySchedule the staff Timeline shows on a phone), fed by the
 *          sub-scoped by-day endpoint with the crew pinned server-side, plus a "not yet scheduled"
 *          list of crew releases that carry no install date (which the day view cannot show).
 *          Tapping any card pushes /sub/releases/:id; back returns here at the same scroll.
 * exports:
 *   SubcontractorJobLog: Page component, rendered inside SubcontractorShell's Outlet.
 * imports_from: [react, react-router-dom, ../services/subPortalApi, ../hooks/useScrollRestore,
 *                ../components/installSchedule/DaySchedule, ../components/sub/SubEmpty]
 * imported_by: [App.jsx]
 * invariants:
 *   - No crew picker: the crew is the account's, chosen by an admin. The header names it so an
 *     empty calendar reads as "nothing scheduled for Saul 2" rather than as a broken page.
 *   - ONE time control: a chip row — "Upcoming" (the rolling ±2-week window with past-due triage)
 *     and a run of calendar months. A month shows every day of that month; the labels stop being
 *     relative ("Tomorrow") because the window no longer starts today.
 *   - Reuses DaySchedule unchanged (roster = the one crew) — the sub timeline must not grow its own
 *     lane/day logic, or the staff tower work reworks it (ROADMAP T3, 2026-09-07 note).
 *   - Polls while visible so a PM's reschedule shows up without a reload.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useOutletContext } from 'react-router-dom';
import DaySchedule from '../components/installSchedule/DaySchedule';
import SubEmpty from '../components/sub/SubEmpty';
import { useScrollRestore } from '../hooks/useScrollRestore';
import { getSubDaySchedule, getSubReleases } from '../services/subPortalApi';

const POLL_MS = 60000;

/** Month chips: last month through four months out, keyed 'YYYY-MM'. */
function monthOptions(today = new Date()) {
    const out = [];
    for (let i = -1; i <= 4; i += 1) {
        const d = new Date(today.getFullYear(), today.getMonth() + i, 1);
        const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
        const label = d.toLocaleDateString('en-US', i === 0 || d.getFullYear() === today.getFullYear()
            ? { month: 'short' } : { month: 'short', year: '2-digit' });
        out.push({ key, label, isCurrent: i === 0 });
    }
    return out;
}

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
    const navigate = useNavigate();
    const crew = subcontractor?.installer_team || null;
    const [data, setData] = useState(null);
    const [releases, setReleases] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [showUnscheduled, setShowUnscheduled] = useState(false);
    const [month, setMonth] = useState(null); // null = Upcoming
    const months = useMemo(() => monthOptions(), []);
    const scrollRef = useScrollRestore(`sub-job-log:${month || 'upcoming'}`, !loading && !!data);

    const load = useCallback(async (silent = false) => {
        if (!silent) setLoading(true);
        setError(null);
        try {
            const [env, feed] = await Promise.all([
                getSubDaySchedule({ days: 14, pastDays: 14, month }),
                getSubReleases(),
            ]);
            setData(env);
            setReleases(feed.releases || []);
        } catch (e) {
            setError(e?.response?.data?.error || e.message || 'Failed to load your schedule');
        } finally {
            setLoading(false);
        }
    }, [month]);

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
    const openId = useCallback((id) => navigate(`/sub/releases/${id}`), [navigate]);
    const openCard = useCallback((card) => openId(card.release_id), [openId]);

    const nothing = data && !data.past_due.length && data.summary.scheduled === 0;

    return (
        <div ref={scrollRef} className="flex-1 min-h-0 overflow-y-auto flex flex-col">
            <div className="sub-page-head">
                <h1>Job Log</h1>
                <div className="sub-ctx">
                    {crew
                        ? `${crew} · ${month ? months.find((m) => m.key === month)?.label || month : 'next 2 weeks'}`
                        : 'No crew assigned'}
                </div>
            </div>
            {crew && (
                <div className="sub-months" role="tablist" aria-label="Time window">
                    <button type="button" role="tab" aria-selected={month === null} className={month === null ? 'active' : ''} onClick={() => setMonth(null)}>Upcoming</button>
                    {months.map((m) => (
                        <button key={m.key} type="button" role="tab" aria-selected={month === m.key}
                            className={month === m.key ? 'active' : ''} onClick={() => setMonth(m.key)}>
                            {m.label}
                        </button>
                    ))}
                </div>
            )}

            {!crew && (
                <SubEmpty icon="calendar" title="No crew assigned yet"
                    body="Your account is not linked to an installer crew, so there is nothing to show. Ask MHMW to assign your crew." />
            )}
            {loading && <div className="text-ink-3 text-sm px-4 py-2">Loading your schedule…</div>}
            {error && <div className="text-red-600 text-sm px-4 py-2">{error}</div>}

            {!loading && !error && crew && nothing && unscheduled.length === 0 && (
                <SubEmpty icon="calendar" title="Nothing scheduled" body={month ? `No installs for ${crew} in ${months.find((m) => m.key === month)?.label || month}.` : `No installs for ${crew} in the next two weeks.`} />
            )}
            {/* Plain block wrapper (not a flex column): DaySchedule's inner overflow div then sizes
                to its content and THIS page scrolls, so sticky day headers, the unscheduled list and
                scroll restore all work against one scroll container. */}
            {!loading && !error && data && crew && !nothing && (
                <div className="px-4">
                    <DaySchedule data={data} roster={roster} crewFilter={crew} onOpenRelease={openCard} relativeLabels={!month} />
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
                            {unscheduled.map((r) => <UnscheduledCard key={r.id} rel={r} onOpen={openId} />)}
                        </div>
                    )}
                </section>
            )}

        </div>
    );
}
