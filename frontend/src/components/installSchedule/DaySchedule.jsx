/**
 * @milehigh-header
 * schema_version: 2
 * purpose: The Installation Schedule as a VERTICAL CALENDAR — days are rows, installs are cards
 *   inside a day, soonest first. This is the phone-shaped answer to the Timeline: GanttChart freezes
 *   392px of lane chrome (STAGING_PX + SIDEBAR_PX) left of its first date column, which is wider than
 *   a phone, so on a handset the whole viewport is chrome. Pivoting the axes removes the chrome
 *   entirely — the crew stops being an axis and becomes a chip on the card — and leaves vertical
 *   scrolling, which is the one gesture a phone is actually good at.
 * exports:
 *   DaySchedule: the day-row list. Presentational; the parent owns fetching, filtering and the modal.
 * imports_from: [react, ./DatePill, ../../utils/installScheduleFormat, ../../utils/crewColor]
 * imported_by: [../../pages/InstallSchedule.jsx]
 * invariants:
 *   - PAST DUE is pinned above today rather than given day rows of its own, so the list opens on what
 *     is next without hiding what was missed. The backend admits only hard/ASAP dates there (a
 *     slipped projection is a stale formula, not a broken promise).
 *   - A multi-day install renders ONCE, on its start day, with a span chip. Repeating it across the
 *     days it covers makes one 3-day job read as three jobs.
 *   - Empty WEEKDAYS render as a thin one-liner so the shape of the week survives; empty WEEKENDS are
 *     dropped entirely (four blank rows per fortnight is just scrolling). A weekend that DOES carry an
 *     install still renders — the rule is about blank rows, not about weekends being unimportant.
 *   - TAPPING A CARD opens the release hub — the SAME modal a Job Log row or the Timeline opens. A
 *     release must not have a different identity depending on which surface you reached it from, so
 *     this view has no detail sheet of its own. The parent owns the modal because it is the thing
 *     that survives a filter change.
 *   - This view carries NO filter chrome of its own. The crew picker lives in the parent's single
 *     control row: on a phone the chip row it replaced cost a whole band of screen above the fold,
 *     which is most of what "the filtering takes up so much room" meant.
 */
import { useMemo } from 'react';
import { DatePill } from './DatePill';
import { fmtDate, fmtHours } from '../../utils/installScheduleFormat';
import { buildCrewColors, UNASSIGNED_CREW } from '../../utils/crewColor';

const NEUTRAL_CREW_COLOR = 'rgb(148 163 184)';   // slate-400, for a crew with no palette slot
const UNASSIGNED_COLOR = 'rgb(245 158 11)';      // amber-500 — a gap to fill, not a crew

/** "Today" / "Tomorrow" / "Thu, Sep 10" — a relative label beats a date the reader has to compare. */
function dayLabel(row, index) {
    if (row.is_today) return 'Today';
    if (index === 1) return 'Tomorrow';
    const d = new Date(`${row.date}T00:00:00`);
    return isNaN(d) ? row.date : d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
}

function daysOverdue(iso, todayIso) {
    const a = new Date(`${iso}T00:00:00`);
    const b = new Date(`${todayIso}T00:00:00`);
    if (isNaN(a) || isNaN(b)) return 0;
    return Math.round((b - a) / 86400000);
}

function CrewChip({ crew, color }) {
    if (crew === UNASSIGNED_CREW) {
        return (
            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] font-semibold bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300">
                Unassigned
            </span>
        );
    }
    return (
        <span className="inline-flex items-center gap-1 font-medium text-ink-2">
            <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: color }} aria-hidden="true" />
            {crew}
        </span>
    );
}

function InstallCard({ card, color, overdueBy, onOpen }) {
    const label = `${card.code} ${card.project_name || ''}. Open release details.`;
    return (
        <div
            role="button"
            tabIndex={0}
            aria-label={label}
            onClick={() => onOpen && onOpen(card)}
            onKeyDown={(e) => {
                if (onOpen && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); onOpen(card); }
            }}
            className="rounded-lg border border-hairline bg-surface shadow-sm p-3 text-left transition-transform active:scale-[0.995] cursor-pointer"
            style={{ borderLeftWidth: 4, borderLeftColor: card.crew === UNASSIGNED_CREW ? UNASSIGNED_COLOR : color }}
        >
            <div className="flex items-start justify-between gap-2">
                <span className="font-mono text-sm font-bold text-accent-600 dark:text-accent-400">{card.code}</span>
                <div className="flex items-center gap-1.5 shrink-0">
                    {overdueBy > 0 && (
                        <span className="px-1.5 py-0.5 rounded text-[11px] font-bold bg-red-600 text-white">
                            {overdueBy}d late
                        </span>
                    )}
                    <DatePill kind={card.date_kind} />
                </div>
            </div>

            {card.project_name && (
                <div className="mt-0.5 text-sm font-medium text-ink break-words">{card.project_name}</div>
            )}

            <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-2">
                <CrewChip crew={card.crew} color={color} />
                <span>⏱ {fmtHours(card.est_hours)}</span>
                {card.span_days > 1 && (
                    <span title={`Through ${fmtDate(card.comp_eta)}`}>📆 {card.span_days} days</span>
                )}
                {overdueBy > 0 && <span className="text-ink-3">was {fmtDate(card.start_install)}</span>}
                {card.stage && <span className="text-ink-3 truncate max-w-[10rem]">{card.stage}</span>}
            </div>

            {card.notes && (
                <div className="mt-2 text-xs text-ink-3 line-clamp-2 break-words">{card.notes}</div>
            )}
        </div>
    );
}

function PastDue({ cards, todayIso, colorFor, onOpen }) {
    if (!cards.length) return null;
    return (
        <section className="rounded-xl border border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-950/30 p-2">
            <h2 className="px-1 py-1 text-xs font-extrabold uppercase tracking-wide text-red-700 dark:text-red-300">
                ⚠ Past due · {cards.length}
            </h2>
            <div className="flex flex-col gap-2">
                {cards.map((c) => (
                    <InstallCard
                        key={`${c.release_id}-overdue`}
                        card={c}
                        color={colorFor(c.crew)}
                        overdueBy={daysOverdue(c.start_install, todayIso)}
                        onOpen={onOpen}
                    />
                ))}
            </div>
        </section>
    );
}

function DayRow({ row, index, colorFor, onOpen }) {
    const empty = row.card_count === 0;
    // Blank weekends are pure scrolling; blank weekdays carry the shape of the week.
    if (empty && row.is_weekend) return null;

    return (
        <section>
            <header
                className={`sticky top-0 z-10 flex items-baseline justify-between gap-2 px-1 py-1.5 bg-canvas/95 backdrop-blur ${
                    row.is_today ? 'border-b-2 border-accent-500' : 'border-b border-hairline'
                }`}
            >
                <span className={`text-sm font-bold ${row.is_today ? 'text-accent-600 dark:text-accent-400' : 'text-ink'}`}>
                    {dayLabel(row, index)}
                </span>
                <span className="text-[11px] text-ink-3 tabular-nums shrink-0">
                    {empty ? 'nothing scheduled' : (
                        <>
                            {row.card_count} {row.card_count === 1 ? 'install' : 'installs'}
                            {row.known_hours > 0 && ` · ${row.known_hours}h`}
                            {row.unknown_hours_count > 0 && ` (+${row.unknown_hours_count}?)`}
                        </>
                    )}
                </span>
            </header>

            {!empty && (
                <div className="flex flex-col gap-2 pt-2 pb-3">
                    {row.cards.map((c) => (
                        <InstallCard key={c.release_id} card={c} color={colorFor(c.crew)} overdueBy={0} onOpen={onOpen} />
                    ))}
                </div>
            )}
        </section>
    );
}

export default function DaySchedule({ data, roster = [], crewFilter = null, onOpenRelease = null }) {
    // Memoised so the colour map is not rebuilt on every render (a fresh [] literal each pass
    // would invalidate it), which would remount the chip dots on each poll.
    const crews = useMemo(() => data?.summary?.crews || [], [data]);
    const colors = useMemo(() => buildCrewColors(roster, crews), [roster, crews]);
    const colorFor = (crew) => colors.get(crew) || NEUTRAL_CREW_COLOR;

    if (!data) return null;

    const todayIso = data.window?.today;
    const nothingAtAll = !data.past_due.length && data.summary.scheduled === 0;

    return (
        <div className="flex-1 min-h-0 overflow-y-auto -mx-1 px-1">
            <div className="flex flex-col gap-1">
                <PastDue cards={data.past_due} todayIso={todayIso} colorFor={colorFor} onOpen={onOpenRelease} />

                {nothingAtAll ? (
                    <p className="py-8 text-center text-sm text-ink-3">
                        Nothing scheduled to install in this window
                        {crewFilter ? ` for ${crewFilter}` : ''}.
                    </p>
                ) : (
                    data.days.map((row, i) => (
                        <DayRow key={row.date} row={row} index={i} colorFor={colorFor} onOpen={onOpenRelease} />
                    ))
                )}
            </div>
        </div>
    );
}
