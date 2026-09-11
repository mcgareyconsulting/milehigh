/**
 * Installation Schedule page — the control row and the release hub.
 *
 * Two things here are load-bearing on a phone and easy to regress:
 *
 *   * THE CONTROL ROW IS ONE ROW, and the crew picker is the only filter in it. It replaced a chip
 *     row plus three range buttons plus a stat wall, which together took most of a phone screen
 *     before the first card — the complaint that prompted this view.
 *   * A PHONE IS CLAMPED TO THE CALENDAR. Crew columns scroll sideways, which is the same unusable
 *     shape as the Timeline. The clamp has to beat the stored preference, or someone who last chose
 *     Crews at a desk opens the page on a phone and is stranded with the toggle hidden.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

const getDaySchedule = vi.hoisted(() => vi.fn());
const getNextWeekSchedule = vi.hoisted(() => vi.fn());
vi.mock('../services/installScheduleApi', () => ({
    getDaySchedule: (...a) => getDaySchedule(...a),
    getNextWeekSchedule: (...a) => getNextWeekSchedule(...a),
}));

const roster = vi.hoisted(() => ({ teams: ['Octavio', 'Saul 2', 'Oscar'] }));
vi.mock('../services/jobsApi', () => ({
    jobsApi: { getInstallerTeams: () => Promise.resolve(roster.teams) },
}));

const releases = vi.hoisted(() => ({ jobs: [] }));
vi.mock('../context/ReleasesContext', () => ({
    useReleases: () => ({ jobs: releases.jobs, refetch: vi.fn() }),
}));

const bp = vi.hoisted(() => ({ isMobile: true }));
vi.mock('../hooks/useBreakpoint', () => ({ useBreakpoint: () => bp }));

const hubProps = vi.hoisted(() => ({ current: null }));
vi.mock('../components/ReleaseHubModal', () => ({
    ReleaseHubModal: (props) => { hubProps.current = props; return props.isOpen ? <div>HUB OPEN</div> : null; },
}));

import InstallSchedule from './InstallSchedule';

// This jsdom runs on an opaque origin, so `localStorage` is absent rather than empty. The page
// already treats storage as best-effort; the tests need a real one to seed the stored view choice.
const store = new Map();
vi.stubGlobal('localStorage', {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, String(v)),
    removeItem: (k) => store.delete(k),
    clear: () => store.clear(),
});

const dayEnvelope = (over = {}) => ({
    window: { start: '2026-08-27', end: '2026-09-24', today: '2026-09-10', days: 14, past_days: 14, installer: null },
    summary: { total_releases: 1, scheduled: 1, past_due: 0, hard_dates: 1, asap_dates: 0,
               unassigned_releases: 0, releases_missing_hours: 0, crews: ['Octavio', 'Saul 2'] },
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
    ...over,
});

beforeEach(() => {
    vi.clearAllMocks();
    roster.teams = ['Octavio', 'Saul 2', 'Oscar'];
    bp.isMobile = true;
    releases.jobs = [];
    hubProps.current = null;
    localStorage.clear();
    getDaySchedule.mockResolvedValue(dayEnvelope());
    getNextWeekSchedule.mockResolvedValue({ window: {}, summary: {}, crews: [] });
});

describe('InstallSchedule', () => {
    it('lists every installer on the roster, not just the ones with work this window', async () => {
        // The window only mentions Octavio and Saul 2; Oscar is idle but still an installer.
        render(<InstallSchedule />);

        const select = await screen.findByLabelText('Filter by installer');
        const options = [...select.querySelectorAll('option')].map((o) => o.textContent);
        expect(options).toEqual(['All installers', 'Octavio', 'Saul 2', 'Oscar']);
    });

    it('takes one installer at a time', async () => {
        render(<InstallSchedule />);
        const select = await screen.findByLabelText('Filter by installer');

        expect(select.multiple).toBe(false);
    });

    it('refetches scoped to the installer that was picked', async () => {
        render(<InstallSchedule />);
        const select = await screen.findByLabelText('Filter by installer');

        const { fireEvent } = await import('@testing-library/react');
        fireEvent.change(select, { target: { value: 'Saul 2' } });

        await waitFor(() => {
            expect(getDaySchedule).toHaveBeenLastCalledWith(
                expect.objectContaining({ installer: 'Saul 2' }),
            );
        });
    });

    it('keeps the full list after filtering, so you can switch straight to another installer', async () => {
        render(<InstallSchedule />);
        const select = await screen.findByLabelText('Filter by installer');
        const { fireEvent } = await import('@testing-library/react');

        // The scoped response mentions only the crew that was asked for — which is exactly what
        // would collapse a picker built from the response instead of the roster.
        getDaySchedule.mockResolvedValue(dayEnvelope({
            summary: { ...dayEnvelope().summary, crews: ['Saul 2'] },
        }));
        fireEvent.change(select, { target: { value: 'Saul 2' } });

        await waitFor(() => expect(getDaySchedule).toHaveBeenLastCalledWith(
            expect.objectContaining({ installer: 'Saul 2' }),
        ));

        const options = [...select.querySelectorAll('option')].map((o) => o.textContent);
        expect(options).toEqual(['All installers', 'Octavio', 'Saul 2', 'Oscar']);
    });

    it('offers Unassigned only once something is actually unassigned', async () => {
        getDaySchedule.mockResolvedValue(dayEnvelope({
            summary: { ...dayEnvelope().summary, crews: ['Octavio', 'Unassigned'] },
        }));
        render(<InstallSchedule />);

        const select = await screen.findByLabelText('Filter by installer');
        await waitFor(() => {
            const options = [...select.querySelectorAll('option')].map((o) => o.textContent);
            // Sorts last — it is a gap to fill, not a person.
            expect(options[options.length - 1]).toBe('Unassigned');
        });
    });

    it('folds the stat wall into one line rather than tiles', async () => {
        getDaySchedule.mockResolvedValue(dayEnvelope({
            summary: { ...dayEnvelope().summary, past_due: 2, scheduled: 36, asap_dates: 1 },
        }));
        render(<InstallSchedule />);

        expect(await screen.findByText(/2 past due/)).toBeInTheDocument();
        expect(screen.getByText(/36 scheduled/)).toBeInTheDocument();
    });

    it('hides the Crews toggle on a phone and serves the calendar anyway', async () => {
        localStorage.setItem('mhmw:install-schedule-view', 'crew');   // last choice made at a desk
        render(<InstallSchedule />);

        await waitFor(() => expect(getDaySchedule).toHaveBeenCalled());
        expect(getNextWeekSchedule).not.toHaveBeenCalled();
        expect(screen.queryByRole('button', { name: 'Crews' })).not.toBeInTheDocument();
    });

    it('shows the Crews toggle once there is room for it', async () => {
        bp.isMobile = false;
        render(<InstallSchedule />);

        expect(await screen.findByRole('button', { name: 'Crews' })).toBeInTheDocument();
    });

    it('opens the shared release hub on the full job-log row when it is loaded', async () => {
        releases.jobs = [{ id: 77, 'Job #': 560, 'Release #': '941', viewer_url: '/v/77' }];
        render(<InstallSchedule />);

        (await screen.findByRole('button', { name: /560-941/ })).click();

        await waitFor(() => expect(screen.getByText('HUB OPEN')).toBeInTheDocument());
        expect(hubProps.current.releaseId).toBe(77);
        expect(hubProps.current.viewerUrl).toBe('/v/77');
    });

    it('still opens the hub when the row is not in the shared dataset', async () => {
        releases.jobs = [];   // e.g. archived, or a partial first page
        render(<InstallSchedule />);

        (await screen.findByRole('button', { name: /560-941/ })).click();

        await waitFor(() => expect(screen.getByText('HUB OPEN')).toBeInTheDocument());
        expect(hubProps.current.releaseId).toBe(77);
    });
});
