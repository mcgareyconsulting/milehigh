/**
 * The Timeline's pinned Unassigned staging column (T1b).
 *
 * Covers what the column is FOR: it must show exactly the releases that are finished in the shop
 * and have nobody scheduled, and it must not double as a dumping ground for everything upstream.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';

// The timeline pulls in the PDF markup stack and several heavy modals that have nothing to do with
// the staging column. Stub them so the test exercises the chart itself.
vi.mock('./ReleaseHubModal', () => ({ ReleaseHubModal: () => null }));
vi.mock('./PdfMarkupModal', () => ({ PdfMarkupModal: () => null }));

vi.mock('../utils/auth', () => ({ checkAuth: () => Promise.resolve({ is_admin: false }) }));
vi.mock('../services/jobsApi', () => ({
    jobsApi: { getInstallerTeams: () => Promise.resolve(['Crew A', 'Crew B']) },
}));

const mockJobs = vi.hoisted(() => ({ current: [] }));
vi.mock('../context/ReleasesContext', () => ({
    useReleases: () => ({ jobs: mockJobs.current, loading: false }),
}));

import GanttChart from './GanttChart';

const rel = (over = {}) => ({
    id: over.id ?? Math.floor(Math.random() * 1e6),
    'Job #': 560,
    'Release #': '923',
    'Job': 'Alta Metro',
    'Description': 'Bldg C stair',
    'Stage': 'Paint Complete',
    'Start install': null,
    start_install_formulaTF: true,
    start_install_asap: false,
    installer: null,
    ...over,
});

const staging = (container) => container.querySelector('[data-staging-tray]');
const lane = (container, name) => container.querySelector(`[data-lane="${name}"]`);

beforeEach(() => {
    mockJobs.current = [];
    globalThis.fetch = vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({ orders: [] }) }));
});

const renderChart = async () => {
    const view = render(<GanttChart />);
    // The installer-team fetch resolves on a microtask; let the roster land before asserting.
    await screen.findByText('Crew A');
    return view;
};

describe('Unassigned staging column', () => {
    it('shows a ready-to-ship release that has no installer', async () => {
        mockJobs.current = [rel({ id: 1, 'Release #': '923' })];
        await renderChart();
        expect(screen.getByText('560-923')).toBeInTheDocument();
        expect(screen.getByText('1 ready to schedule')).toBeInTheDocument();
    });

    it('leaves out a release that already has a crew — it belongs in that crew\'s lane', async () => {
        mockJobs.current = [rel({ id: 1, 'Release #': '923', installer: 'Crew A' })];
        await renderChart();
        expect(screen.getByText('0 ready to schedule')).toBeInTheDocument();
    });

    it('leaves out upstream drafting and fab rows so the column stays a work surface', async () => {
        mockJobs.current = [
            rel({ id: 1, 'Release #': 'ready', Stage: 'Store at MHMW' }),
            rel({ id: 2, 'Release #': 'cutting', Stage: 'Cut Start' }),
            rel({ id: 3, 'Release #': 'drafting', Stage: 'Released' }),
        ];
        await renderChart();
        expect(screen.getByText('1 ready to schedule')).toBeInTheDocument();
        expect(screen.getByText('560-ready')).toBeInTheDocument();
        expect(screen.queryByText('560-cutting')).not.toBeInTheDocument();
    });

    it('floats an ASAP release to the top of the tray and flags it', async () => {
        mockJobs.current = [
            rel({ id: 1, 'Job #': 100, 'Release #': 'normal' }),
            rel({ id: 2, 'Job #': 900, 'Release #': 'rush', start_install_asap: true }),
        ];
        const { container } = await renderChart();
        const cards = within(staging(container)).getAllByRole('button');
        expect(within(cards[0]).getByText('900-rush')).toBeInTheDocument();
        expect(within(cards[0]).getByText('ASAP')).toBeInTheDocument();
        expect(within(cards[1]).getByText('100-normal')).toBeInTheDocument();
    });

    it('says so plainly when nothing is waiting', async () => {
        mockJobs.current = [rel({ id: 1, installer: 'Crew A' })];
        await renderChart();
        expect(screen.getByText(/Everything ready to ship has a crew/i)).toBeInTheDocument();
    });

    it('still mirrors a Ship Planning release into its shipping lane while it waits', async () => {
        // Same raw row in two places, exactly like the installer mirror: waiting for a crew in the
        // tray, and shown on its ship date in the Shipping Planning lane.
        mockJobs.current = [rel({
            id: 1, 'Release #': '923', Stage: 'Ship Planning',
            'Start install': '2026-09-10', start_install_formulaTF: false,
        })];
        const { container } = await renderChart();
        expect(within(staging(container)).getByText('560-923')).toBeInTheDocument();
        expect(within(lane(container, 'Shipping Planning')).getByText(/560-923/)).toBeInTheDocument();
    });
});
