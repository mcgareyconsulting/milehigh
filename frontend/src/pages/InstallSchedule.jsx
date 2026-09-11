/**
 * @milehigh-header
 * schema_version: 2
 * purpose: Installation schedule in two shapes off one endpoint family. CREW columns is the
 *          production-meeting view — active releases with a start_install in the coming N days,
 *          grouped into Trello-shaped cards by crew, hard dates first, flagging crews with
 *          overlapping hard dates or an overloaded week. DAY rows is the vertical calendar for
 *          phones, where the Timeline's frozen lane chrome does not fit.
 * exports:
 *   InstallSchedule: Page component (any authenticated user). Owns fetching, window and view state.
 * imports_from: [react, ../services/installScheduleApi, ../utils/installScheduleFormat,
 *   ../hooks/useBreakpoint, ../hooks/useDaySchedule, ../components/installSchedule/DatePill,
 *   ../components/installSchedule/DaySchedule, ../components/installSchedule/CrewSelect,
 *   ../components/ReleaseHubModal]
 * imported_by: [App.jsx]
 * invariants:
 *   - Read-only view. Estimated hours come only from the manual install_hrs field; blanks render "—".
 *   - date_kind drives the pill color, mirroring the Job Log StartInstallEditor convention. The pill
 *     lives in ./installSchedule/DatePill so the two views cannot disagree about a release.
 *   - The Crew/Day choice is STICKY, seeded once from the viewport width at first mount and then
 *     remembered. It is deliberately NOT reactive to width: an iPhone crossing 768px on rotate would
 *     otherwise swap the mounted tree mid-scroll, which is the BUG-14 failure documented in
 *     utils/viewportView.js. Rotating the device must never change which view you are reading.
 *   - Fetch state lives here, above the view swap, so toggling or rotating never strands a
 *     half-loaded child. The release-hub modal lives here too, for the same reason: it must outlive
 *     a crew-filter change, which refetches and rebuilds the whole list underneath it.
 *   - PHONES ARE CLAMPED TO THE CALENDAR. Crew columns are a horizontally-scrolled desk layout; on a
 *     handset they are the same unusable shape as the Timeline. The clamp is reactive (unlike the
 *     stored preference, which stays sticky) so that someone who last chose Crews on a desktop is not
 *     stranded on a phone with the toggle hidden.
 *   - ONE control row, and the installer picker is the only filter in it. A native <select> rather
 *     than a chip row: it collapses N installers into one line, and on iOS it opens the system
 *     picker, which is a better target than a 28px chip. Its options come from the ROSTER, not from
 *     the current (filtered) response — see hooks/useDaySchedule.
 *   - Tapping a card opens the shared release hub. The card payload is deliberately slim, so the full
 *     row is looked up in the shared ReleasesContext by id; when it isn't loaded we still open on the
 *     bare job/release (mirroring GanttChart.openOrderHub) rather than making the tap do nothing.
 *   - The day-view fetch and that lookup live in hooks/useDaySchedule, shared with the Job Log's
 *     Timeline, which renders the same calendar in place on a phone. One fetch path, so the two
 *     surfaces cannot drift into showing different installs for the same day.
 */
import { useState, useEffect, useCallback } from 'react';
import { getNextWeekSchedule } from '../services/installScheduleApi';
import { useBreakpoint } from '../hooks/useBreakpoint';
import { useDaySchedule, useReleaseHub } from '../hooks/useDaySchedule';
import { DatePill } from '../components/installSchedule/DatePill';
import { fmtDate, fmtHours } from '../utils/installScheduleFormat';
import DaySchedule from '../components/installSchedule/DaySchedule';
import CrewSelect from '../components/installSchedule/CrewSelect';
import { ReleaseHubModal } from '../components/ReleaseHubModal';

const VIEW_KEY = 'mhmw:install-schedule-view';
const DAY_VIEW_PAST_DAYS = 14;
const RANGE_OPTIONS = [7, 14, 31];

const SELECT_CLS = 'px-2.5 py-1.5 text-sm rounded-lg bg-surface text-ink border border-hairline '
    + 'focus:outline-none focus:ring-2 focus:ring-accent-500 min-w-0';

/** Seed the view once: phones open on the calendar, everything else on crew columns. */
function initialView() {
    try {
        const stored = localStorage.getItem(VIEW_KEY);
        if (stored === 'day' || stored === 'crew') return stored;
    } catch { /* storage disabled — fall through to the width guess */ }
    return typeof window !== 'undefined' && window.innerWidth < 768 ? 'day' : 'crew';
}

function Stat({ label, value, tone = '' }) {
    return (
        <div className="flex flex-col items-center px-4 py-2 rounded-lg bg-surface shadow-sm border border-hairline">
            <span className={`text-2xl font-bold ${tone}`}>{value}</span>
            <span className="text-xs text-ink-3 uppercase tracking-wide">{label}</span>
        </div>
    );
}

// One Trello-shaped card: crew · code · project · install date · duration.
function ReleaseCard({ card, conflictCodes }) {
    const inConflict = conflictCodes.has(card.code);
    return (
        <div className={`rounded-lg border p-3 bg-surface shadow-sm ${
            inConflict ? 'border-red-400 dark:border-red-500' : 'border-hairline'
        }`}>
            <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-sm font-bold text-accent-600 dark:text-accent-400">{card.code}</span>
                <DatePill kind={card.date_kind} />
            </div>
            <div className="mt-1 text-sm font-medium text-ink truncate" title={card.project_name}>
                {card.project_name}
            </div>
            <div className="mt-2 flex items-center justify-between text-xs text-ink-2">
                <span>📅 {fmtDate(card.start_install)}{card.comp_eta && card.comp_eta !== card.start_install ? ` → ${fmtDate(card.comp_eta)}` : ''}</span>
                <span className="font-semibold">⏱ {fmtHours(card.est_hours)}</span>
            </div>
            {inConflict && (
                <div className="mt-2 text-xs font-semibold text-red-600 dark:text-red-400">⚠ Overlapping hard date</div>
            )}
        </div>
    );
}

function CrewColumn({ crew }) {
    const conflictCodes = new Set(crew.conflicts.flat());
    return (
        <div className="flex-shrink-0 w-72 flex flex-col">
            <div className={`rounded-t-lg px-3 py-2 ${
                crew.is_unassigned ? 'bg-amber-500' : 'bg-accent-600'
            } text-white`}>
                <div className="flex items-center justify-between">
                    <span className="font-bold truncate">{crew.crew}</span>
                    <span className="text-xs opacity-90">{crew.card_count} {crew.card_count === 1 ? 'install' : 'installs'}</span>
                </div>
                <div className="mt-1 flex flex-wrap gap-1 text-[11px]">
                    <span className="px-1.5 py-0.5 rounded bg-white/20">
                        {crew.total_known_hours}h / {crew.weekly_capacity_hours}h wk
                        {crew.unknown_hours_count > 0 ? ` (+${crew.unknown_hours_count} unknown)` : ''}
                    </span>
                    {crew.overloaded && <span className="px-1.5 py-0.5 rounded bg-red-600 font-semibold">OVERLOADED</span>}
                    {crew.conflicts.length > 0 && <span className="px-1.5 py-0.5 rounded bg-red-600 font-semibold">{crew.conflicts.length} CONFLICT{crew.conflicts.length > 1 ? 'S' : ''}</span>}
                </div>
            </div>
            <div className="flex-1 flex flex-col gap-2 p-2 rounded-b-lg bg-surface-2 min-h-[120px] border-x border-b border-hairline">
                {crew.cards.map((c) => (
                    <ReleaseCard key={c.release_id} card={c} conflictCodes={conflictCodes} />
                ))}
            </div>
        </div>
    );
}

function ViewToggle({ view, onChange }) {
    return (
        <div className="inline-flex rounded-lg border border-hairline overflow-hidden shrink-0">
            {[['day', 'Calendar'], ['crew', 'Crews']].map(([key, label]) => (
                <button
                    key={key}
                    type="button"
                    onClick={() => onChange(key)}
                    aria-pressed={view === key}
                    className={`px-3 py-1.5 text-sm font-medium ${
                        view === key ? 'bg-accent-600 text-white' : 'bg-surface text-ink-2 hover:bg-surface-2'
                    }`}
                >
                    {label}
                </button>
            ))}
        </div>
    );
}

export default function InstallSchedule() {
    const [days, setDays] = useState(14);
    const [view, setView] = useState(initialView);
    const [crewFilter, setCrewFilter] = useState(null);

    const { isMobile } = useBreakpoint();
    // Crew columns scroll sideways; that is the very shape that does not fit a phone.
    const isDay = view === 'day' || isMobile;

    // Day view: the shared hook, so this page and the Job Log Timeline read one source.
    const dayView = useDaySchedule({
        days, pastDays: DAY_VIEW_PAST_DAYS, installer: crewFilter, enabled: isDay,
    });
    const { hubJob, openRelease, closeHub } = useReleaseHub();

    // Crew view keeps its own fetch — a different endpoint and a different envelope shape.
    const [crewData, setCrewData] = useState(null);
    const [crewLoading, setCrewLoading] = useState(false);
    const [crewError, setCrewError] = useState(null);

    const loadCrews = useCallback(async (d) => {
        setCrewLoading(true);
        setCrewError(null);
        try {
            setCrewData(await getNextWeekSchedule(d));
        } catch (e) {
            setCrewError(e?.response?.data?.error || e.message || 'Failed to load schedule');
        } finally {
            setCrewLoading(false);
        }
    }, []);

    useEffect(() => { if (!isDay) loadCrews(days); }, [isDay, days, loadCrews]);

    const data = isDay ? dayView.data : crewData;
    const loading = isDay ? dayView.loading : crewLoading;
    const error = isDay ? dayView.error : crewError;
    const roster = dayView.roster;
    const reload = () => (isDay ? dayView.reload() : loadCrews(days));

    const chooseView = (next) => {
        if (next === view) return;
        setView(next);
        try { localStorage.setItem(VIEW_KEY, next); } catch { /* preference is best-effort */ }
    };

    const s = data?.summary;

    return (
        <div className="flex flex-col h-[calc(100vh_-_var(--app-chrome-h))] bg-canvas p-3 sm:p-4 gap-2 sm:gap-3 overflow-hidden">
            {/* Title + the one number that changes what someone does today. The crew view keeps its
                stat wall below; the calendar folds it into this line, because seven tiles was most of
                a phone screen before the first card. */}
            <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                    <h1 className="text-lg sm:text-xl font-bold text-ink">Installation Schedule</h1>
                    {s && isDay && (
                        <p className="text-xs sm:text-sm text-ink-3">
                            {s.past_due > 0 && (
                                <span className="text-red-600 dark:text-red-400 font-semibold">{s.past_due} past due · </span>
                            )}
                            {s.scheduled} scheduled
                            {s.asap_dates > 0 && <span className="text-red-600 dark:text-red-400"> · {s.asap_dates} ASAP</span>}
                            {` · next ${data.window.days} days`}
                        </p>
                    )}
                    {data?.window && !isDay && (
                        <p className="text-xs sm:text-sm text-ink-3">
                            {fmtDate(data.window.start)} – {fmtDate(data.window.end)} · hard dates first
                        </p>
                    )}
                </div>
                <button
                    onClick={reload}
                    aria-label="Refresh schedule"
                    className="shrink-0 px-3 py-1.5 text-sm rounded-lg bg-surface text-ink-2 hover:bg-surface-2 border border-hairline notif-pod-reserve"
                >
                    ↻
                </button>
            </div>

            {/* One control row. Crew is the only filter. */}
            <div className="flex items-center gap-2 flex-wrap">
                {isDay && (
                    <CrewSelect
                        crews={dayView.crewOptions}
                        value={crewFilter}
                        onChange={setCrewFilter}
                        className="flex-1 max-w-[16rem]"
                    />
                )}
                <select
                    value={days}
                    onChange={(e) => setDays(Number(e.target.value))}
                    aria-label="Days to show"
                    className={SELECT_CLS}
                >
                    {RANGE_OPTIONS.map((d) => <option key={d} value={d}>{d} days</option>)}
                </select>
                {/* Hidden on phones, where the Crews layout is the unusable shape this view exists
                    to replace. */}
                {!isMobile && <ViewToggle view={view} onChange={chooseView} />}
            </div>

            {s && !isDay && (
                <div className="flex flex-wrap gap-2">
                    <Stat label="Releases" value={s.total_releases} />
                    <Stat label="Hard dates" value={s.hard_dates} tone="text-green-600 dark:text-green-400" />
                    <Stat label="Projected" value={s.projected_dates} tone="text-ink-3" />
                    <Stat label="Unassigned" value={s.unassigned_releases} tone={s.unassigned_releases ? 'text-amber-600 dark:text-amber-400' : ''} />
                    <Stat label="Overloaded crews" value={s.overloaded_crews} tone={s.overloaded_crews ? 'text-red-600 dark:text-red-400' : ''} />
                    <Stat label="Conflicts" value={s.crews_with_conflicts} tone={s.crews_with_conflicts ? 'text-red-600 dark:text-red-400' : ''} />
                    {s.releases_missing_hours > 0 && <Stat label="Missing hours" value={s.releases_missing_hours} tone="text-amber-600 dark:text-amber-400" />}
                </div>
            )}

            {loading && <div className="text-ink-3">Loading schedule…</div>}
            {error && <div className="text-red-600 dark:text-red-400">{error}</div>}

            {!loading && !error && data && isDay && (
                <DaySchedule
                    data={data}
                    roster={roster}
                    crewFilter={crewFilter}
                    onOpenRelease={openRelease}
                />
            )}

            {!loading && !error && data && !isDay && (
                data.crews.length === 0
                    ? <div className="text-ink-3">No releases scheduled to install in this window.</div>
                    : (
                        <div className="flex-1 flex gap-4 overflow-x-auto pb-2">
                            {data.crews.map((crew) => <CrewColumn key={crew.crew} crew={crew} />)}
                        </div>
                    )
            )}

            {/* The SAME modal a Job Log row or the Timeline opens — one release, one identity. */}
            <ReleaseHubModal
                isOpen={!!hubJob}
                job={hubJob}
                releaseId={hubJob?.id}
                viewerUrl={hubJob?.viewer_url}
                initialTab="details"
                onClose={closeHub}
                onJobUpdate={reload}
            />
        </div>
    );
}
