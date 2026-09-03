/**
 * One release, one identity.
 *
 * The Timeline used to open its own modals — ReleaseCockpitModal for admins, ReleaseDetailModal for
 * everyone else — while a Job Log row opened ReleaseHubModal. Same release, three different faces
 * depending on where you clicked it and who you were. These tests pin the fix: every entry point on
 * the Timeline opens the Job Log's modal, and nothing about it varies by role.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';

vi.mock('./PdfMarkupModal', () => ({ PdfMarkupModal: () => null }));

// Capture what the hub is handed, so "same modal" can be asserted on props, not just presence.
const hubProps = vi.hoisted(() => ({ calls: [] }));
vi.mock('./ReleaseHubModal', () => ({
    ReleaseHubModal: (props) => {
        hubProps.calls.push(props);
        return props.isOpen ? <div data-testid="release-hub">{props.job?.['Job #']}-{props.job?.['Release #']}</div> : null;
    },
}));

const authUser = vi.hoisted(() => ({ current: { is_admin: true } }));
vi.mock('../utils/auth', () => ({ checkAuth: () => Promise.resolve(authUser.current) }));
vi.mock('../services/jobsApi', () => ({
    jobsApi: { getInstallerTeams: () => Promise.resolve(['Crew A']), updateStartInstall: vi.fn() },
}));

const mockJobs = vi.hoisted(() => ({ current: [] }));
vi.mock('../context/ReleasesContext', () => ({
    useReleases: () => ({
        jobs: mockJobs.current, loading: false, patchJob: vi.fn(), refreshMaterialSummary: vi.fn(),
    }),
}));

import GanttChart from './GanttChart';

const rel = (over = {}) => ({
    id: 7,
    'Job #': 560,
    'Release #': '923',
    'Job': 'Alta Metro',
    'Description': 'Bldg C stair',
    'Stage': 'Paint Complete',
    'Start install': null,
    start_install_formulaTF: true,
    start_install_asap: false,
    installer: null,
    viewer_url: 'https://example.test/viewer',
    ...over,
});

const lastOpen = () => [...hubProps.calls].reverse().find((p) => p.isOpen);

beforeEach(() => {
    hubProps.calls = [];
    mockJobs.current = [];
    authUser.current = { is_admin: true };
    globalThis.fetch = vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({ orders: [] }) }));
});

const renderChart = async () => {
    const view = render(<GanttChart />);
    await screen.findByText('Crew A');
    return view;
};

describe('the Timeline opens the Job Log\'s modal', () => {
    it('a staging-tray card opens the release hub, carrying the whole row', async () => {
        mockJobs.current = [rel()];
        const { container } = await renderChart();

        fireEvent.click(container.querySelector('[data-staging-tray] [role="button"]'));

        expect(screen.getByTestId('release-hub')).toHaveTextContent('560-923');
        const props = lastOpen();
        expect(props.releaseId).toBe(7);
        expect(props.viewerUrl).toBe('https://example.test/viewer');
        expect(props.initialTab).toBe('details');
    });

    it('a shipping-lane card opens the same hub', async () => {
        mockJobs.current = [rel({
            Stage: 'Ship Planning', 'Start install': '2026-09-10', start_install_formulaTF: false, installer: 'Crew A',
        })];
        const { container } = await renderChart();

        const lane = container.querySelector('[data-lane="Shipping Planning"]');
        fireEvent.click(within(lane).getByText(/560-923/));

        expect(screen.getByTestId('release-hub')).toBeInTheDocument();
        expect(lastOpen().releaseId).toBe(7);
    });

    it('an installer-lane bar opens the same hub', async () => {
        mockJobs.current = [rel({
            'Start install': '2026-09-10', start_install_formulaTF: false, installer: 'Crew A',
        })];
        const { container } = await renderChart();

        const lane = container.querySelector('[data-lane="Crew A"]');
        fireEvent.click(within(lane).getByText(/560-923/));

        expect(screen.getByTestId('release-hub')).toBeInTheDocument();
        expect(lastOpen().releaseId).toBe(7);
    });

    it('does not open a different modal for a non-admin', async () => {
        authUser.current = { is_admin: false };
        mockJobs.current = [rel()];
        const { container } = await renderChart();

        fireEvent.click(container.querySelector('[data-staging-tray] [role="button"]'));

        // Same component, same props shape — role changes drag rights, never the release's identity.
        expect(screen.getByTestId('release-hub')).toHaveTextContent('560-923');
        expect(lastOpen().releaseId).toBe(7);
    });

    it('opens the hub closed by default — nothing is shown until a card is clicked', async () => {
        mockJobs.current = [rel()];
        await renderChart();
        expect(screen.queryByTestId('release-hub')).not.toBeInTheDocument();
    });

    it('closing the hub clears the materials scroll, so the next open starts on Details', async () => {
        mockJobs.current = [rel()];
        const { container } = await renderChart();

        fireEvent.click(container.querySelector('[data-staging-tray] [role="button"]'));
        expect(lastOpen().scrollToMaterials).toBe(false);
        lastOpen().onClose();

        fireEvent.click(container.querySelector('[data-staging-tray] [role="button"]'));
        expect(lastOpen().scrollToMaterials).toBe(false);
    });
});
