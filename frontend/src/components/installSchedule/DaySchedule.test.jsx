/**
 * The vertical calendar — the phone-shaped Installation Schedule.
 *
 * The Timeline freezes 392px of lane chrome (GanttChart STAGING_PX + SIDEBAR_PX) before its first
 * date column, so on a handset the grid is unreachable. This view pivots the axes: days are rows and
 * the crew becomes a chip. These tests pin the three rendering rules that a well-meaning refactor
 * would plausibly reverse, each of which makes the list unreadable on a small screen:
 *
 *   * a MULTI-DAY install renders once, on its start day (repeating it makes one job read as three),
 *   * empty WEEKENDS vanish but empty WEEKDAYS stay as one-liners (the week keeps its shape without
 *     four blank rows per fortnight),
 *   * PAST DUE sits above today rather than scattered into rows the reader has to scroll back for.
 *
 * Tapping a card opens the shared release hub rather than a detail sheet of this view's own, so the
 * test pins that the whole card is the target — not a "Details" link a thumb has to find.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import DaySchedule from './DaySchedule';

const card = (over = {}) => ({
    release_id: over.release_id ?? 1,
    code: '560-941',
    project_name: 'Alta Metro Bld B',
    crew: 'Octavio',
    unassigned: false,
    start_install: '2026-09-10',
    date_kind: 'hard',
    is_hard: true,
    est_hours: 16,
    comp_eta: '2026-09-10',
    span_days: 1,
    stage: 'Ship Planning',
    notes: null,
    ...over,
});

const day = (date, over = {}) => ({
    date,
    weekday: new Date(`${date}T00:00:00`).toLocaleDateString('en-US', { weekday: 'short' }),
    is_today: false,
    is_weekend: [0, 6].includes(new Date(`${date}T00:00:00`).getDay()),
    card_count: (over.cards || []).length,
    known_hours: 0,
    unknown_hours_count: 0,
    cards: [],
    ...over,
    ...( over.cards ? { card_count: over.cards.length } : {} ),
});

const envelope = (over = {}) => ({
    window: { start: '2026-08-27', end: '2026-09-24', today: '2026-09-10', days: 14, past_days: 14, installer: null },
    summary: { total_releases: 0, scheduled: 0, past_due: 0, hard_dates: 0, asap_dates: 0,
               unassigned_releases: 0, releases_missing_hours: 0, crews: ['Octavio'] },
    past_due: [],
    days: [],
    ...over,
});

const noop = () => {};

describe('DaySchedule', () => {
    it('renders an install on its own day row', () => {
        render(<DaySchedule
            data={envelope({
                summary: { ...envelope().summary, scheduled: 1 },
                days: [day('2026-09-10', { is_today: true, cards: [card()], known_hours: 16 })],
            })}
            roster={['Octavio']} crewFilter={null} onOpenRelease={noop}
        />);

        expect(screen.getByText('Today')).toBeInTheDocument();
        expect(screen.getByText('560-941')).toBeInTheDocument();
        expect(screen.getByText('Alta Metro Bld B')).toBeInTheDocument();
        expect(screen.getByText(/1 install\b/)).toBeInTheDocument();
    });

    it('shows a multi-day install once, on its start day, with a span chip', () => {
        const data = envelope({
            summary: { ...envelope().summary, scheduled: 1 },
            days: [
                day('2026-09-10', { is_today: true, cards: [card({ span_days: 3, comp_eta: '2026-09-12' })] }),
                day('2026-09-11'),
                day('2026-09-12'),
            ],
        });
        render(<DaySchedule data={data} roster={['Octavio']} crewFilter={null} onOpenRelease={noop} />);

        expect(screen.getAllByText('560-941')).toHaveLength(1);
        expect(screen.getByText(/3 days/)).toBeInTheDocument();
        // The days it spans stay empty rather than repeating the card. Only Fri shows a
        // one-liner — Sat 9/12 is a weekend, so an empty one is dropped outright.
        expect(screen.getAllByText('nothing scheduled')).toHaveLength(1);
    });

    it('keeps empty weekdays as one-liners but drops empty weekends', () => {
        render(<DaySchedule
            data={envelope({
                summary: { ...envelope().summary, scheduled: 1 },
                days: [
                    day('2026-09-10', { is_today: true }),   // Thu, empty -> one-liner
                    day('2026-09-11'),                       // Fri, empty -> one-liner
                    day('2026-09-12'),                       // Sat, empty -> dropped
                    day('2026-09-13'),                       // Sun, empty -> dropped
                    day('2026-09-14', { cards: [card({ start_install: '2026-09-14' })] }),
                ],
            })}
            roster={['Octavio']} crewFilter={null} onOpenRelease={noop}
        />);

        expect(screen.getAllByText('nothing scheduled')).toHaveLength(2);
        expect(screen.queryByText(/Sat, Sep 12/)).not.toBeInTheDocument();
        expect(screen.queryByText(/Sun, Sep 13/)).not.toBeInTheDocument();
        expect(screen.getByText('560-941')).toBeInTheDocument();
    });

    it('renders a weekend day that actually carries an install', () => {
        render(<DaySchedule
            data={envelope({
                summary: { ...envelope().summary, scheduled: 1 },
                days: [day('2026-09-12', { cards: [card({ start_install: '2026-09-12' })] })],
            })}
            roster={['Octavio']} crewFilter={null} onOpenRelease={noop}
        />);

        expect(screen.getByText('560-941')).toBeInTheDocument();
    });

    it('pins past due above the day rows and counts how late each one is', () => {
        render(<DaySchedule
            data={envelope({
                summary: { ...envelope().summary, past_due: 1 },
                past_due: [card({ release_id: 9, code: '555-110', start_install: '2026-09-03' })],
                days: [day('2026-09-10', { is_today: true })],
            })}
            roster={['Octavio']} crewFilter={null} onOpenRelease={noop}
        />);

        const banner = screen.getByRole('heading', { name: /Past due/ });
        expect(banner).toHaveTextContent('1');
        expect(screen.getByText('555-110')).toBeInTheDocument();
        expect(screen.getByText('7d late')).toBeInTheDocument();
    });

    it('marks an unassigned release rather than colouring it as a crew', () => {
        render(<DaySchedule
            data={envelope({
                summary: { ...envelope().summary, scheduled: 1, crews: ['Octavio', 'Unassigned'] },
                days: [day('2026-09-10', { is_today: true, cards: [card({ crew: 'Unassigned', unassigned: true })] })],
            })}
            roster={['Octavio']} crewFilter={null} onOpenRelease={noop}
        />);

        expect(screen.getByText('Unassigned')).toBeInTheDocument();
    });

    it('renders "—" for hours nobody entered, never a fabricated 0h', () => {
        render(<DaySchedule
            data={envelope({
                summary: { ...envelope().summary, scheduled: 1 },
                days: [day('2026-09-10', { is_today: true, cards: [card({ est_hours: null })], unknown_hours_count: 1 })],
            })}
            roster={['Octavio']} crewFilter={null} onOpenRelease={noop}
        />);

        expect(screen.getByText('⏱ —')).toBeInTheDocument();
    });

    it('opens the release hub when the card is tapped anywhere', () => {
        const onOpenRelease = vi.fn();
        const c = card();
        render(<DaySchedule
            data={envelope({
                summary: { ...envelope().summary, scheduled: 1 },
                days: [day('2026-09-10', { is_today: true, cards: [c] })],
            })}
            roster={['Octavio']} crewFilter={null} onOpenRelease={onOpenRelease}
        />);

        // The whole card is the target — a phone has no room for a hit-me link.
        screen.getByRole('button', { name: /560-941/ }).click();
        expect(onOpenRelease).toHaveBeenCalledWith(expect.objectContaining({ release_id: c.release_id }));
    });

    it('opens the hub from a past-due card too', () => {
        const onOpenRelease = vi.fn();
        render(<DaySchedule
            data={envelope({
                summary: { ...envelope().summary, past_due: 1 },
                past_due: [card({ release_id: 9, code: '555-110', start_install: '2026-09-03' })],
                days: [day('2026-09-10', { is_today: true })],
            })}
            roster={['Octavio']} crewFilter={null} onOpenRelease={onOpenRelease}
        />);

        screen.getByRole('button', { name: /555-110/ }).click();
        expect(onOpenRelease).toHaveBeenCalledWith(expect.objectContaining({ release_id: 9 }));
    });

    it('says so plainly when the window is genuinely empty', () => {
        render(<DaySchedule
            data={envelope({ days: [day('2026-09-10', { is_today: true })] })}
            roster={[]} crewFilter={null} onOpenRelease={noop}
        />);

        expect(screen.getByText(/Nothing scheduled to install/)).toBeInTheDocument();
    });
});
