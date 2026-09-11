/**
 * The release hub on a phone.
 *
 * The hub lays the Activity rail out as a FIXED 346px column beside a `minmax(0,1fr)` pane. That is
 * fine at a desk and catastrophic at 390px: the pane collapsed to a ~40px ribbon of single-letter
 * lines while the rail overflowed across it, and the two read as one broken, overlapping surface.
 * Worse, the header's right-hand cluster was `shrink-0`, so it starved the title block down to about
 * 28px (the job-release label wrapped one number per line) and pushed the CLOSE BUTTON off the panel
 * — leaving the backdrop as the only way out of a modal opened from a card tap.
 *
 * These tests pin the narrow-screen contract: rail becomes a tab, close stays reachable, and the
 * desktop layout is untouched.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const bp = vi.hoisted(() => ({ isMobile: true }));
vi.mock('../hooks/useBreakpoint', () => ({ useBreakpoint: () => bp }));

vi.mock('../services/jobsApi', () => ({
    jobsApi: {
        getMaterialOrders: vi.fn(() => Promise.resolve({ orders: [] })),
        getReleasePhotos: vi.fn(() => Promise.resolve([])),
        getReleaseChecklist: vi.fn(() => Promise.resolve({ todos: [], meetings: [] })),
        getInstallerTeams: vi.fn(() => Promise.resolve(['Team 1'])),
        getNotesHistory: vi.fn(() => Promise.resolve({ events: [] })),
        getBBReview: vi.fn(() => Promise.resolve(null)),
        updateNotes: vi.fn(() => Promise.resolve({})),
        updateStage: vi.fn(() => Promise.resolve({})),
        updateJobFields: vi.fn(() => Promise.resolve({})),
    },
}));
vi.mock('../services/notificationApi', () => ({ fetchMentionableUsers: vi.fn(() => Promise.resolve([])) }));
vi.mock('../utils/auth', () => ({ checkAuth: vi.fn(() => Promise.resolve({ is_admin: true, is_drafter: true })) }));

import { ReleaseHubModal } from './ReleaseHubModal.jsx';

const JOB = {
    id: 42,
    'Job #': '170',
    'Release #': '561',
    Job: 'Garrett - Banyan High Point',
    Description: 'Bearing Angles',
    Stage: 'Fitup Complete',
    'Stage Group': 'FABRICATION',
    PM: 'RL',
    BY: 'DCR',
    Notes: 'NEED CO',
    trello_card_id: 'abc123',
    viewer_url: '',
};

const open = (props = {}) =>
    render(<ReleaseHubModal isOpen job={JOB} releaseId={42} onClose={() => {}} {...props} />);

beforeEach(() => {
    bp.isMobile = true;
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ versions: [], photos: [], events: [] }),
    })));
});

afterEach(() => vi.clearAllMocks());

describe('ReleaseHubModal on a phone', () => {
    it('offers Activity as a tab instead of a side column', async () => {
        open();
        expect(await screen.findByRole('tab', { name: /Activity/ })).toBeInTheDocument();
    });

    it('keeps the close button reachable', async () => {
        const onClose = vi.fn();
        open({ onClose });

        fireEvent.click(await screen.findByLabelText('Close'));
        expect(onClose).toHaveBeenCalled();
    });

    it('shows the job-release label on one line, not one number per line', async () => {
        open();
        // A single text node holding "170-561" — when the block was starved this wrapped.
        const label = await screen.findByText('170-561');
        expect(label.className).toContain('whitespace-nowrap');
    });

    it('opens the notes rail when the Activity tab is chosen', async () => {
        open();

        fireEvent.click(await screen.findByRole('tab', { name: /Activity/ }));

        await waitFor(() => {
            expect(screen.getAllByText(/Activity/).length).toBeGreaterThan(1);
        });
    });

    it('drops the Attachments tab when there is no release id to fetch with', async () => {
        render(<ReleaseHubModal isOpen job={JOB} releaseId={null} onClose={() => {}} />);

        expect(await screen.findByRole('tab', { name: /Activity/ })).toBeInTheDocument();
        expect(screen.queryByRole('tab', { name: /Attachments/ })).not.toBeInTheDocument();
    });
});

describe('ReleaseHubModal at a desk', () => {
    beforeEach(() => { bp.isMobile = false; });

    it('keeps the rail as a column and adds no Activity tab', async () => {
        open();

        await screen.findByRole('tab', { name: 'Details' });
        expect(screen.queryByRole('tab', { name: /Activity/ })).not.toBeInTheDocument();
        // The rail still renders — as the column, beside the pane.
        expect(screen.getByText('Activity')).toBeInTheDocument();
    });
});
