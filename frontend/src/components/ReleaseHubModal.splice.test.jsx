// A splice has no Procore submittal or Trello card of its own (T9: zero Trello
// interaction), so the release modal's header links on a splice are carbon copies of
// its ORIGINAL's — whether the splice was reached from the original's Splices tab or
// opened straight from the Job Log.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ReleaseHubModal } from './ReleaseHubModal.jsx';
import { jobsApi } from '../services/jobsApi';

vi.mock('../services/jobsApi', () => ({
    jobsApi: {
        getMaterialOrders: vi.fn(() => Promise.resolve({ orders: [] })),
        getReleasePhotos: vi.fn(() => Promise.resolve([])),
        getReleaseChecklist: vi.fn(() => Promise.resolve({ todos: [], meetings: [] })),
        getInstallerTeams: vi.fn(() => Promise.resolve([])),
        getNotesHistory: vi.fn(() => Promise.resolve({ events: [] })),
        getSplices: vi.fn(() => Promise.resolve({ splices: [] })),
        getRelease: vi.fn(),
    },
}));
vi.mock('../services/notificationApi', () => ({
    fetchMentionableUsers: vi.fn(() => Promise.resolve([])),
}));
vi.mock('../utils/auth', () => ({
    checkAuth: vi.fn(() => Promise.resolve({ is_admin: false, is_drafter: false })),
    readCachedRoleFlags: vi.fn(() => ({ isAdmin: false, canSeeReport: false, canUseBBChat: false })),
}));
// The Splices tab has its own suite; here it is just the doorway to a splice.
vi.mock('./SplicesPane', () => ({
    SplicesPane: ({ onOpenRelease }) => (
        <button type="button" onClick={() => onOpenRelease(SPLICE.id)}>open splice</button>
    ),
}));

const PROCORE = 'https://app.procore.com/webclients/host/companies/18521/projects/777/tools/submittals/4242';

const ORIGINAL = {
    id: 1,
    'Job #': '340',
    'Release #': '666',
    Job: 'Alta Metro',
    Description: 'Stair',
    Stage: 'Released',
    trello_card_id: 'card-orig',
    procore_project_id: '777',
    procore_submittal_id: '4242',
    parent_release_id: null,
    viewer_url: '',
};
const SPLICE = {
    id: 2,
    'Job #': '340',
    'Release #': '666.1',
    Job: 'Alta Metro',
    Description: 'Stair — level 2 rails',
    Stage: 'Released',
    trello_card_id: null,
    procore_project_id: null,
    procore_submittal_id: null,
    parent_release_id: 1,
    viewer_url: '',
};

beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
        ok: true, json: () => Promise.resolve({ versions: [], photos: [], events: [] }),
    })));
    jobsApi.getRelease.mockImplementation((id) => Promise.resolve(id === 1 ? ORIGINAL : SPLICE));
});
afterEach(() => {
    vi.clearAllMocks();
    vi.unstubAllGlobals();
});

const expectOriginalLinks = () => {
    expect(screen.getByText('Procore').closest('a')).toHaveAttribute('href', PROCORE);
    expect(screen.getByText('Trello').closest('a')).toHaveAttribute('href', 'https://trello.com/c/card-orig');
    expect(screen.getByText('Trello').closest('a')).toHaveAttribute('title', expect.stringMatching(/original, 340-666$/));
};

describe('ReleaseHubModal — splice header links', () => {
    it("a splice opened from the Job Log fetches its original and borrows its links", async () => {
        render(<ReleaseHubModal isOpen onClose={() => {}} job={SPLICE} releaseId={SPLICE.id} />);
        await waitFor(() => expect(screen.getByText('Trello').tagName).toBe('A'));
        expect(jobsApi.getRelease).toHaveBeenCalledWith(1);
        expectOriginalLinks();
    });

    it('a splice reached from the original reuses the row in hand — no refetch of it', async () => {
        render(<ReleaseHubModal isOpen onClose={() => {}} job={ORIGINAL} releaseId={ORIGINAL.id} />);
        fireEvent.click(screen.getByRole('tab', { name: /Splices/ }));
        fireEvent.click(screen.getByText('open splice'));
        await screen.findByText('666.1', { exact: false });
        await waitFor(() => expect(screen.getByText('Trello').tagName).toBe('A'));
        expectOriginalLinks();
        expect(jobsApi.getRelease).not.toHaveBeenCalledWith(1);
    });

    it('keeps the links inert until the original arrives, and when it cannot be fetched', async () => {
        jobsApi.getRelease.mockImplementation(() => Promise.reject(new Error('gone')));
        render(<ReleaseHubModal isOpen onClose={() => {}} job={SPLICE} releaseId={SPLICE.id} />);
        await waitFor(() => expect(jobsApi.getRelease).toHaveBeenCalledWith(1));
        // Never the splice's own (empty) ids, never a link to nowhere.
        expect(screen.getByText('Trello').tagName).not.toBe('A');
        expect(screen.getByText('Procore').tagName).not.toBe('A');
    });

    it("an original still uses its own links, with no borrowed-link hint", () => {
        render(<ReleaseHubModal isOpen onClose={() => {}} job={ORIGINAL} releaseId={ORIGINAL.id} />);
        expect(screen.getByText('Procore').closest('a')).toHaveAttribute('href', PROCORE);
        expect(screen.getByText('Trello').closest('a')).not.toHaveAttribute('title');
        expect(jobsApi.getRelease).not.toHaveBeenCalled();
    });
});
