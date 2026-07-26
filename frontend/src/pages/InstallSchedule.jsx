/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Next-week installation schedule for the production meeting. Pulls active releases with a
 *          start_install in the coming N days, groups them into Trello-shaped cards by crew, pins hard
 *          (green) dates first, and flags crews with overlapping hard dates or an overloaded week.
 * exports:
 *   InstallSchedule: Page component (any authenticated user).
 * imports_from: [react, ../services/installScheduleApi]
 * imported_by: [App.jsx]
 * invariants:
 *   - Read-only view. Estimated hours come only from the manual install_hrs field; blanks render as "—".
 *   - date_kind drives the pill color, mirroring the Job Log StartInstallEditor convention.
 */
import { useState, useEffect, useCallback } from 'react';
import { getNextWeekSchedule } from '../services/installScheduleApi';

const DATE_KIND = {
    hard: { label: 'Hard', cls: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300 ring-1 ring-green-400/50' },
    asap: { label: 'ASAP', cls: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300 ring-1 ring-red-400/50' },
    projected: { label: 'Projected', cls: 'bg-gray-100 text-gray-600 dark:bg-slate-700 dark:text-slate-300 ring-1 ring-gray-300/50' },
    neutral: { label: 'Done', cls: 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400' },
};

const fmtDate = (iso) => {
    if (!iso) return '—';
    const d = new Date(`${iso}T00:00:00`);
    return isNaN(d) ? iso : d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
};

const fmtHours = (h) => (h === null || h === undefined ? '—' : `${h}h`);

function DatePill({ kind }) {
    const meta = DATE_KIND[kind] || DATE_KIND.projected;
    return <span className={`inline-block px-2 py-0.5 rounded text-xs font-semibold ${meta.cls}`}>{meta.label}</span>;
}

function Stat({ label, value, tone = '' }) {
    return (
        <div className="flex flex-col items-center px-4 py-2 rounded-lg bg-white dark:bg-slate-800 shadow-sm">
            <span className={`text-2xl font-bold ${tone}`}>{value}</span>
            <span className="text-xs text-gray-500 dark:text-slate-400 uppercase tracking-wide">{label}</span>
        </div>
    );
}

// One Trello-shaped card: crew · code · project · install date · duration.
function ReleaseCard({ card, conflictCodes }) {
    const inConflict = conflictCodes.has(card.code);
    return (
        <div className={`rounded-lg border p-3 bg-white dark:bg-slate-800 shadow-sm ${
            inConflict ? 'border-red-400 dark:border-red-500' : 'border-gray-200 dark:border-slate-700'
        }`}>
            <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-sm font-bold text-accent-600 dark:text-accent-400">{card.code}</span>
                <DatePill kind={card.date_kind} />
            </div>
            <div className="mt-1 text-sm font-medium text-gray-800 dark:text-slate-100 truncate" title={card.project_name}>
                {card.project_name}
            </div>
            <div className="mt-2 flex items-center justify-between text-xs text-gray-600 dark:text-slate-300">
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
            <div className="flex-1 flex flex-col gap-2 p-2 rounded-b-lg bg-gray-50 dark:bg-slate-900/50 min-h-[120px]">
                {crew.cards.map((c) => (
                    <ReleaseCard key={c.release_id} card={c} conflictCodes={conflictCodes} />
                ))}
            </div>
        </div>
    );
}

export default function InstallSchedule() {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [days, setDays] = useState(7);

    const load = useCallback(async (d) => {
        setLoading(true);
        setError(null);
        try {
            setData(await getNextWeekSchedule(d));
        } catch (e) {
            setError(e?.response?.data?.error || e.message || 'Failed to load schedule');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { load(days); }, [days, load]);

    const s = data?.summary;

    return (
        <div className="flex flex-col h-full p-4 gap-4 overflow-hidden">
            <div className="flex items-center justify-between flex-wrap gap-3">
                <div>
                    <h1 className="text-xl font-bold text-gray-900 dark:text-slate-100">Installation Schedule</h1>
                    {data?.window && (
                        <p className="text-sm text-gray-500 dark:text-slate-400">
                            {fmtDate(data.window.start)} – {fmtDate(data.window.end)} · hard dates first
                        </p>
                    )}
                </div>
                <div className="flex items-center gap-2">
                    {[7, 14, 31].map((d) => (
                        <button
                            key={d}
                            onClick={() => setDays(d)}
                            className={`px-3 py-1.5 text-sm rounded-lg font-medium transition-colors ${
                                days === d
                                    ? 'bg-accent-600 text-white'
                                    : 'bg-white dark:bg-slate-800 text-gray-700 dark:text-slate-200 hover:bg-gray-100 dark:hover:bg-slate-700'
                            }`}
                        >
                            {d} days
                        </button>
                    ))}
                    <button
                        onClick={() => load(days)}
                        className="px-3 py-1.5 text-sm rounded-lg bg-white dark:bg-slate-800 text-gray-700 dark:text-slate-200 hover:bg-gray-100 dark:hover:bg-slate-700"
                    >
                        ↻ Refresh
                    </button>
                </div>
            </div>

            {s && (
                <div className="flex flex-wrap gap-2">
                    <Stat label="Releases" value={s.total_releases} />
                    <Stat label="Hard dates" value={s.hard_dates} tone="text-green-600 dark:text-green-400" />
                    <Stat label="Projected" value={s.projected_dates} tone="text-gray-500" />
                    <Stat label="Unassigned" value={s.unassigned_releases} tone={s.unassigned_releases ? 'text-amber-600 dark:text-amber-400' : ''} />
                    <Stat label="Overloaded crews" value={s.overloaded_crews} tone={s.overloaded_crews ? 'text-red-600 dark:text-red-400' : ''} />
                    <Stat label="Conflicts" value={s.crews_with_conflicts} tone={s.crews_with_conflicts ? 'text-red-600 dark:text-red-400' : ''} />
                    {s.releases_missing_hours > 0 && <Stat label="Missing hours" value={s.releases_missing_hours} tone="text-amber-600 dark:text-amber-400" />}
                </div>
            )}

            {loading && <div className="text-gray-500 dark:text-slate-400">Loading schedule…</div>}
            {error && <div className="text-red-600 dark:text-red-400">{error}</div>}
            {!loading && !error && data && data.crews.length === 0 && (
                <div className="text-gray-500 dark:text-slate-400">No releases scheduled to install in this window.</div>
            )}

            {!loading && !error && data && data.crews.length > 0 && (
                <div className="flex-1 flex gap-4 overflow-x-auto pb-2">
                    {data.crews.map((crew) => (
                        <CrewColumn key={crew.crew} crew={crew} />
                    ))}
                </div>
            )}
        </div>
    );
}
