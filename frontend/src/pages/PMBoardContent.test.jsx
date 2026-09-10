/**
 * The Timeline on a phone.
 *
 * GanttChart freezes 392px of chrome (STAGING_PX + SIDEBAR_PX) left of its first date column, which
 * is wider than a phone viewport — so on a handset every visible pixel is chrome and the grid itself
 * is unreachable. Below `md` this route renders the vertical day calendar instead.
 *
 * The rule these tests exist to hold: it renders IN PLACE. An earlier pass showed a link out to
 * /install-schedule, which dropped the reader out of the Job Log shell — losing the toolbar, the
 * filters and the Table/Timeline switch — in order to read what is still the Timeline. The vertical
 * column is this view on a phone, not a pointer to a different page.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

const outlet = vi.hoisted(() => ({ loading: false, fetchError: null }));
vi.mock('react-router-dom', () => ({ useOutletContext: () => outlet }));

const bp = vi.hoisted(() => ({ isMobile: true }));
vi.mock('../hooks/useBreakpoint', () => ({ useBreakpoint: () => bp }));

vi.mock('../components/GanttChart', () => ({ default: () => <div>GANTT</div> }));
vi.mock('../components/ReleaseHubModal', () => ({
    ReleaseHubModal: (p) => (p.isOpen ? <div>HUB OPEN</div> : null),
}));

const getDaySchedule = vi.hoisted(() => vi.fn());
vi.mock('../services/installScheduleApi', () => ({
    getDaySchedule: (...a) => getDaySchedule(...a),
    getNextWeekSchedule: vi.fn(),
}));
vi.mock('../services/jobsApi', () => ({
    jobsApi: { getInstallerTeams: () => Promise.resolve(['Octavio', 'Saul 2', 'Oscar']) },
}));
vi.mock('../context/ReleasesContext', () => ({
    useReleases: () => ({ jobs: [{ id: 77, 'Job #': 560, 'Release #': '941' }], refetch: vi.fn() }),
}));

import PMBoardContent from './PMBoardContent';

const envelope = {
    window: { start: '2026-08-27', end: '2026-09-24', today: '2026-09-10', days: 14, past_days: 14, installer: null },
    summary: { total_releases: 1, scheduled: 1, past_due: 0, hard_dates: 1, asap_dates: 0,
               unassigned_releases: 0, releases_missing_hours: 0, crews: ['Octavio'] },
    past_due: [],
    days: [{
        date: '2026-09-10', weekday: 'Thu', is_today: true, is_weekend: false,
        card_count: 1, known_hours: 16, unknown_hours_count: 0,
        cards: [{
            release_id: 77, code: '560-941', project_name: 'Alta Metro Bld B', crew: 'Octavio',
            unassigned: false, start_install: '2026-09-10', date_kind: 'hard', is_hard: true,
            est_hours: 16, comp_eta: '2026-09-10', span_days: 1, stage: 'Ship Planning', notes: null,
            job: 560, release: '941',
        }],
    }],
};

beforeEach(() => {
    vi.clearAllMocks();
    bp.isMobile = true;
    outlet.loading = false;
    outlet.fetchError = null;
    getDaySchedule.mockResolvedValue(envelope);
});

describe('Timeline on a phone', () => {
    it('renders the day calendar in place, not the Gantt', async () => {
        render(<PMBoardContent />);

        expect(await screen.findByText('560-941')).toBeInTheDocument();
        expect(screen.getByText('Today')).toBeInTheDocument();
        expect(screen.queryByText('GANTT')).not.toBeInTheDocument();
    });

    it('never sends the reader out to the Installation Schedule page', async () => {
        render(<PMBoardContent />);

        await screen.findByText('560-941');
        expect(screen.queryByText(/Open day calendar/i)).not.toBeInTheDocument();
        // No link out of the Job Log shell at all.
        expect(screen.queryByRole('link')).not.toBeInTheDocument();
    });

    it('carries the installer picker and nothing else', async () => {
        render(<PMBoardContent />);

        await screen.findByText('560-941');
        // Whose work you are looking at is the question this view answers, so it earns its line...
        expect(screen.getByLabelText('Filter by installer')).toBeInTheDocument();
        // ...but the shell toolbar is directly above, so nothing else stacks under it.
        expect(screen.queryByLabelText('Days to show')).not.toBeInTheDocument();
        expect(screen.queryByText(/scheduled/)).not.toBeInTheDocument();
    });

    it('lists every installer and takes one at a time', async () => {
        render(<PMBoardContent />);
        await screen.findByText('560-941');

        const select = screen.getByLabelText('Filter by installer');
        expect(select.multiple).toBe(false);
        expect([...select.querySelectorAll('option')].map((o) => o.textContent))
            .toEqual(['All installers', 'Octavio', 'Saul 2', 'Oscar']);
    });

    it('refetches scoped to the installer that was picked', async () => {
        const { fireEvent } = await import('@testing-library/react');
        render(<PMBoardContent />);
        await screen.findByText('560-941');

        fireEvent.change(screen.getByLabelText('Filter by installer'), { target: { value: 'Saul 2' } });

        await waitFor(() => expect(getDaySchedule).toHaveBeenLastCalledWith(
            expect.objectContaining({ installer: 'Saul 2' }),
        ));
    });

    it('opens the shared release hub from a card', async () => {
        render(<PMBoardContent />);

        (await screen.findByRole('button', { name: /560-941/ })).click();
        await waitFor(() => expect(screen.getByText('HUB OPEN')).toBeInTheDocument());
    });
});

describe('Timeline at a desk', () => {
    beforeEach(() => { bp.isMobile = false; });

    it('still renders the Gantt and never fetches the calendar', async () => {
        render(<PMBoardContent />);

        expect(await screen.findByText('GANTT')).toBeInTheDocument();
        expect(getDaySchedule).not.toHaveBeenCalled();
    });
});
